#!/usr/bin/env bash
set -euo pipefail
# ===========================================================================
# platform.sh - governed execution platform: lab mock + API + console + campaigns
#
# Usage:
#   platform.sh up|down|restart|status        # lab mock + API (full platform env)
#   platform.sh console start|stop|status|logs
#   platform.sh campaign list
#   platform.sh campaign run <name|file> [--json]
#
# The API started here carries the FULL platform environment (lab URL, event
# store, policies dir), unlike `api.sh start` which runs the bare Track U API.
# Secrets stay in the environment (R8) - never stored here.
# ===========================================================================

CICD_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${CICD_DIR}/lib/common.sh"

API_SH="${CICD_DIR}/api.sh"
API_PORT_FILE="${RUN_DIR}/api.port"

_port_free() {
    ! ss -ltn 2>/dev/null | awk '{print $4}' | grep -q ":${1}\$"
}

_kill_port_holder() {
    # Policy (R19): the canonical port is enforced, never relocated. If a port
    # is held, the holder is killed so the service binds where it is expected.
    local port="$1"
    local pids
    pids="$(ss -ltnp 2>/dev/null | awk -v p=":${port}" '$4 ~ p"$"' \
        | grep -oP 'pid=\K[0-9]+' | sort -u | tr '\n' ' ')"
    [ -z "${pids// /}" ] && return 0
    warn "port ${port} occupe par pid(s) ${pids}- kill (port canonique impose)"
    # shellcheck disable=SC2086
    kill ${pids} 2>/dev/null || true
    sleep 1
    if ! _port_free "${port}"; then
        # shellcheck disable=SC2086
        kill -9 ${pids} 2>/dev/null || true
        sleep 1
    fi
}

_resolve_api_port() {
    # Canonical port from common.sh; honor an explicit INSPECT_IA_AGENTS_API_PORT env
    # override only. The previous run's api.port is NOT used as a seed: seeding
    # from it made the port creep upward on every restart (8090 -> 8100 -> ...).
    # The port is enforced, not remembered.
    :
}

_pick_api_port() {
    # The canonical port is non-negotiable: if an unrelated process holds it,
    # kill the holder rather than relocate the API (R19).
    if _port_free "${API_PORT}"; then return 0; fi
    _kill_port_holder "${API_PORT}"
    if _port_free "${API_PORT}"; then
        ok "port ${API_PORT} libere"
        return 0
    fi
    err "port ${API_PORT} toujours occupe apres kill"
    exit 1
}

_pid_of() {
    # _pid_of <pid_file> -> echoes pid if alive, else returns 1
    local file="$1"
    [ -f "${file}" ] || return 1
    local pid; pid="$(cat "${file}" 2>/dev/null || true)"
    [ -n "${pid}" ] && kill -0 "${pid}" 2>/dev/null || return 1
    echo "${pid}"
}

_wait_http() {
    # _wait_http <url> <tries> -> 0 when the endpoint answers
    local url="$1" tries="${2:-20}"
    local i
    for ((i = 0; i < tries; i++)); do
        if curl -sf -o /dev/null --max-time 2 "${url}" 2>/dev/null; then
            return 0
        fi
        sleep 0.5
    done
    return 1
}

# --- lab mock ---------------------------------------------------------------

lab_start() {
    if _pid_of "${LAB_PID_FILE}" >/dev/null; then
        warn "lab mock deja en cours (pid $(_pid_of "${LAB_PID_FILE}"))"
        return 0
    fi
    # A healthy lab may already be serving (stale pid file after a race or an
    # external start): adopt it instead of failing on the port bind.
    if curl -sf -o /dev/null --max-time 2 "http://127.0.0.1:${LAB_PORT}/healthz" 2>/dev/null; then
        local lpid
        lpid="$(ss -ltnp 2>/dev/null | awk -v p=":${LAB_PORT}" '$4 ~ p {print $6}' \
            | grep -oP 'pid=\K[0-9]+' | head -1 || true)"
        if [ -n "${lpid}" ]; then echo "${lpid}" >"${LAB_PID_FILE}"; fi
        warn "lab mock deja en service sur :${LAB_PORT} (adopte, pid ${lpid:-inconnu})"
        return 0
    fi
    # Port held by something that is not a healthy lab: kill it, the canonical
    # lab port is enforced, not relocated (R19).
    if ! _port_free "${LAB_PORT}"; then _kill_port_holder "${LAB_PORT}"; fi
    mkdir -p "${RUN_DIR}"
    hdr "START lab mock sur :${LAB_PORT} (11 systemes simules)"
    ( cd "${REPO_ROOT}" \
        && INSPECT_IA_AGENTS_LAB_PORT="${LAB_PORT}" \
           nohup "$(py)" -m recette.lab.mock_server >"${LAB_LOG_FILE}" 2>&1 & \
        echo $! >"${LAB_PID_FILE}" )
    if _wait_http "http://127.0.0.1:${LAB_PORT}/healthz" 20; then
        ok "lab mock pret (pid $(_pid_of "${LAB_PID_FILE}")) - logs: ${LAB_LOG_FILE}"
    else
        err "lab mock ne repond pas - voir ${LAB_LOG_FILE}"
        tail -n 20 "${LAB_LOG_FILE}" 2>/dev/null || true
        exit 1
    fi
}

lab_stop() {
    local pid
    if ! pid="$(_pid_of "${LAB_PID_FILE}")"; then
        info "lab mock non demarre"
        rm -f "${LAB_PID_FILE}"
        return 0
    fi
    hdr "STOP lab mock (pid ${pid})"
    kill "${pid}" 2>/dev/null || true
    rm -f "${LAB_PID_FILE}"
    ok "lab mock arrete"
}

# --- lab mock_local servers (one per target system, started via the API) -----

_lab_servers_start() {
    # Start every mock_local server declared in config/servers THROUGH the API,
    # so app.state.server_manager owns the subprocesses and tears them down on
    # API shutdown (lifespan). Spawning them from the shell would orphan them.
    # Idempotent: a server already up reports its status; we do not relocate it.
    local base="http://${API_HOST}:${API_PORT}"
    local ids
    ids="$(curl -sf --max-time 5 "${base}/config/servers" 2>/dev/null \
        | "$(py)" -c 'import sys,json; print(" ".join(s["id"] for s in json.load(sys.stdin) if s.get("mode") in ("mock_local","honeypot")))' 2>/dev/null || true)"
    if [ -z "${ids}" ]; then
        info "aucun serveur mock_local declare dans la config"
        return 0
    fi
    hdr "START serveurs lab mock_local (cibles des agents)"
    local id status
    for id in ${ids}; do
        status="$(curl -sf --max-time 10 -X POST "${base}/config/servers/${id}/start" 2>/dev/null \
            | "$(py)" -c 'import sys,json; print(json.load(sys.stdin).get("status","?"))' 2>/dev/null || echo error)"
        if [ "${status}" = "up" ]; then
            ok "  ${id} : up"
        else
            warn "  ${id} : ${status} (demarrage echoue -- les runs lies a ce serveur echoueront)"
        fi
    done
}

# --- platform (lab + API with full env) --------------------------------------

platform_up() {
    # Dev convenience: lab domains hot-reload on edit (R5). Exported before
    # lab_start AND before the API start so the :8082 lab and the API-spawned
    # mock_local servers (which inherit the API env) both pick it up. An explicit
    # value wins; the code default stays OFF for tests/replay determinism (I4).
    export INSPECT_IA_AGENTS_LAB_RELOAD="${INSPECT_IA_AGENTS_LAB_RELOAD:-on}"
    lab_start
    mkdir -p "${PLATFORM_DATA_DIR}" "${RUN_DIR}"
    _pick_api_port
    echo "${API_PORT}" >"${API_PORT_FILE}"
    hdr "START API gouvernee sur ${API_HOST}:${API_PORT}"
    # api.sh reads its env at start time: export the platform wiring first.
    export INSPECT_IA_AGENTS_API_PORT="${API_PORT}"
    export INSPECT_IA_AGENTS_LAB_URL="http://127.0.0.1:${LAB_PORT}"
    export INSPECT_IA_AGENTS_EVENT_STORE_PATH="${EVENT_STORE_PATH}"
    export INSPECT_IA_AGENTS_POLICIES_DIR="${POLICIES_DIR}"
    # Proxy side-effect tracing on by default for the dev platform, so the cockpit
    # network log shows the agent <-> server exchange out of the box (R5). An
    # explicit env value (or .env) wins; the code default stays OFF for tests/replay.
    export INSPECT_IA_AGENTS_PROXY_DEBUG="${INSPECT_IA_AGENTS_PROXY_DEBUG:-on}"
    "${API_SH}" start
    if _wait_http "http://${API_HOST}:${API_PORT}/health" 20; then
        _lab_servers_start
        ok "plateforme prete - API http://${API_HOST}:${API_PORT}, lab :${LAB_PORT}"
        info "console : ./recette.sh console start (puis http://localhost:${CONSOLE_PORT})"
    else
        err "API ne repond pas sur /health"
        exit 1
    fi
}

platform_down() {
    "${API_SH}" stop || true
    lab_stop
    if _pid_of "${CONSOLE_PID_FILE}" >/dev/null; then
        console_stop
    fi
    ok "plateforme arretee"
}

platform_purge() {
    # Kill EVERY local web server belonging to THIS repo (and only this repo):
    # recette.api uvicorn instances, lab mocks, vite dev servers -- including
    # strays whose pid files were lost. Never touches docker containers or
    # any process outside the repo.
    hdr "PURGE serveurs locaux du projet"
    platform_down || true
    local patterns=(
        "python -m recette.api"
        "python -m recette.lab.mock_server"
        "${CONSOLE_DIR}.*vite"
    )
    local found=0
    local pat pid args
    for pat in "${patterns[@]}"; do
        while IFS= read -r pid; do
            [ -n "${pid}" ] || continue
            args="$(ps -p "${pid}" -o args= 2>/dev/null || true)"
            # Only processes anchored in this repo (venv path or console dir).
            case "${args}" in
                *"${REPO_ROOT}"*)
                    echo "  kill ${pid}: ${args:0:90}"
                    kill "${pid}" 2>/dev/null || true
                    found=$((found + 1))
                    ;;
            esac
        done < <(pgrep -f "${pat}" 2>/dev/null || true)
    done
    rm -f "${API_PID_FILE}" "${LAB_PID_FILE}" "${CONSOLE_PID_FILE}" "${API_PORT_FILE}"
    if [ "${found}" -eq 0 ]; then
        ok "aucun serveur residuel"
    else
        sleep 1
        ok "${found} processus arretes, pid files nettoyes"
    fi
    info "ports encore ecoutes (pour verification) :"
    ss -ltn 2>/dev/null | awk 'NR>1 {print "   " $4}' | grep -E ":(80[0-9]{2}|5173)$" || echo "   (aucun port projet)"
}

platform_status() {
    hdr "PLATEFORME GOUVERNEE"
    local pid
    if pid="$(_pid_of "${LAB_PID_FILE}")"; then
        ok "lab mock   : pid ${pid}, port ${LAB_PORT}"
    else
        info "lab mock   : arrete"
    fi
    "${API_SH}" status || true
    if pid="$(_pid_of "${CONSOLE_PID_FILE}")"; then
        ok "console    : pid ${pid}, http://localhost:${CONSOLE_PORT}"
    else
        info "console    : arretee"
    fi
    # mock_local lab servers (agent targets): id/system/port from the registry,
    # live up/down from the per-server status endpoint.
    local base="http://${API_HOST}:${API_PORT}"
    local meta
    meta="$(curl -sf --max-time 3 "${base}/config/servers" 2>/dev/null \
        | "$(py)" -c 'import sys,json
for s in json.load(sys.stdin):
    if s.get("mode") in ("mock_local","honeypot"): print(s["id"], s.get("system","?"), s.get("port","?"))' 2>/dev/null || true)"
    if [ -n "${meta}" ]; then
        info "serveurs lab (mock_local + honeypot) :"
        local sid ssys sport sstatus
        while read -r sid ssys sport; do
            [ -n "${sid}" ] || continue
            sstatus="$(curl -sf --max-time 2 "${base}/config/servers/${sid}/status" 2>/dev/null \
                | "$(py)" -c 'import sys,json; print(json.load(sys.stdin).get("status","?"))' 2>/dev/null || echo "?")"
            printf '   %-18s %-13s :%-5s %s\n' "${sid}" "${ssys}" "${sport}" "${sstatus}"
        done <<< "${meta}"
    fi
    sep
    if curl -sf --max-time 2 "http://${API_HOST}:${API_PORT}/audit/verify" 2>/dev/null \
        | "$(py)" -m json.tool 2>/dev/null; then
        :
    else
        info "audit/verify indisponible (API arretee ?)"
    fi
}

# --- console -----------------------------------------------------------------

console_start() {
    if _pid_of "${CONSOLE_PID_FILE}" >/dev/null; then
        warn "console deja en cours (pid $(_pid_of "${CONSOLE_PID_FILE}"))"
        return 0
    fi
    command -v npm >/dev/null 2>&1 || { err "npm introuvable"; exit 1; }
    [ -d "${CONSOLE_DIR}/node_modules" ] || {
        hdr "npm install (premier lancement)"
        ( cd "${CONSOLE_DIR}" && npm install )
    }
    mkdir -p "${RUN_DIR}"
    # Enforce the canonical console port: a stale vite (e.g. one wired to the
    # wrong API) is killed so --strictPort binds 5173 here (R19).
    if ! _port_free "${CONSOLE_PORT}"; then _kill_port_holder "${CONSOLE_PORT}"; fi
    hdr "START console sur :${CONSOLE_PORT} (API: http://${API_HOST}:${API_PORT})"
    ( cd "${CONSOLE_DIR}" \
        && VITE_INSPECT_IA_AGENTS_API_URL="http://${API_HOST}:${API_PORT}" \
           nohup npm run dev -- --port "${CONSOLE_PORT}" --strictPort \
           >"${CONSOLE_LOG_FILE}" 2>&1 & \
        echo $! >"${CONSOLE_PID_FILE}" )
    if _wait_http "http://localhost:${CONSOLE_PORT}" 30; then
        ok "console prete: http://localhost:${CONSOLE_PORT}"
    else
        err "console ne repond pas - voir ${CONSOLE_LOG_FILE}"
        tail -n 20 "${CONSOLE_LOG_FILE}" 2>/dev/null || true
        exit 1
    fi
}

console_stop() {
    local pid
    if ! pid="$(_pid_of "${CONSOLE_PID_FILE}")"; then
        info "console non demarree"
        rm -f "${CONSOLE_PID_FILE}"
        return 0
    fi
    hdr "STOP console (pid ${pid})"
    # npm run dev spawns vite as a child: kill the process group.
    kill -- -"$(ps -o pgid= -p "${pid}" | tr -d ' ')" 2>/dev/null || kill "${pid}" 2>/dev/null || true
    rm -f "${CONSOLE_PID_FILE}"
    ok "console arretee"
}

console_status() {
    local pid
    if pid="$(_pid_of "${CONSOLE_PID_FILE}")"; then
        ok "console en cours (pid ${pid}) - http://localhost:${CONSOLE_PORT}"
    else
        info "console arretee"
    fi
}

console_logs() {
    [ -f "${CONSOLE_LOG_FILE}" ] || { info "pas de logs console"; return 0; }
    tail -n 50 -f "${CONSOLE_LOG_FILE}"
}

# --- campaigns ----------------------------------------------------------------

campaign_list() {
    hdr "CAMPAGNES (${CAMPAIGNS_DIR})"
    ( cd "${REPO_ROOT}" && "$(py)" -m recette.campaign list --dir "${CAMPAIGNS_DIR}" )
}

_campaign_file() {
    # accept a bare name (identity-offboarding), a file name, or a path
    local name="$1"
    if [ -f "${name}" ]; then echo "${name}"; return 0; fi
    if [ -f "${CAMPAIGNS_DIR}/${name}" ]; then echo "${CAMPAIGNS_DIR}/${name}"; return 0; fi
    if [ -f "${CAMPAIGNS_DIR}/${name}.campaign.json" ]; then
        echo "${CAMPAIGNS_DIR}/${name}.campaign.json"; return 0
    fi
    return 1
}

campaign_run() {
    local name="${1:-}"
    [ -n "${name}" ] || { err "usage: platform.sh campaign run <nom|fichier> [--json]"; exit 1; }
    shift
    local file
    file="$(_campaign_file "${name}")" || { err "campagne introuvable: ${name}"; exit 1; }
    if ! curl -sf -o /dev/null --max-time 2 "http://${API_HOST}:${API_PORT}/health" 2>/dev/null; then
        err "API non joignable sur ${API_HOST}:${API_PORT} - lancer: ./recette.sh platform up"
        exit 1
    fi
    local extra=()
    if [ "${1:-}" = "--json" ]; then
        mkdir -p "${CAMPAIGN_REPORTS_DIR}"
        local stamp; stamp="$(date +%Y%m%d-%H%M%S)"
        extra=(--json "${CAMPAIGN_REPORTS_DIR}/$(basename "${file%.campaign.json}")-${stamp}.json")
    fi
    hdr "CAMPAGNE: $(basename "${file}")"
    ( cd "${REPO_ROOT}" \
        && "$(py)" -m recette.campaign run "${file}" \
            --api "http://${API_HOST}:${API_PORT}" "${extra[@]}" )
}

campaign_menu() {
    # interactive picker for the recette.sh menu
    local files=()
    while IFS= read -r f; do files+=("$f"); done \
        < <(find "${CAMPAIGNS_DIR}" -maxdepth 1 -name '*.campaign.json' | sort)
    if [ "${#files[@]}" -eq 0 ]; then
        warn "aucune campagne dans ${CAMPAIGNS_DIR}"
        return 0
    fi
    hdr "Choisir une campagne"
    local i
    for i in "${!files[@]}"; do
        echo -e "   ${GREEN}$((i + 1)))${NC} $(basename "${files[$i]}")"
    done
    echo -n "  Choix : "
    local c; read -r c
    [[ "${c}" =~ ^[0-9]+$ ]] && [ "${c}" -ge 1 ] && [ "${c}" -le "${#files[@]}" ] \
        || { warn "choix invalide"; return 0; }
    campaign_run "${files[$((c - 1))]}" --json
}

# --- dispatch ------------------------------------------------------------------

_resolve_api_port
# Children (api.sh) must see the resolved port, not the common.sh default.
export INSPECT_IA_AGENTS_API_PORT="${API_PORT}"
cmd="${1:-status}"; shift || true
case "${cmd}" in
    up)        platform_up ;;
    down)      platform_down ;;
    restart)   platform_down; platform_up ;;
    status)    platform_status ;;
    purge)     platform_purge ;;
    console)
        sub="${1:-status}"; shift || true
        case "${sub}" in
            start)  console_start ;;
            stop)   console_stop ;;
            status) console_status ;;
            logs)   console_logs ;;
            *) err "usage: platform.sh console start|stop|status|logs"; exit 1 ;;
        esac ;;
    campaign)
        sub="${1:-list}"; shift || true
        case "${sub}" in
            list)  campaign_list ;;
            run)   campaign_run "$@" ;;
            menu)  campaign_menu ;;
            *) err "usage: platform.sh campaign list|run <nom> [--json]"; exit 1 ;;
        esac ;;
    *) err "usage: platform.sh up|down|restart|status|console ...|campaign ..."; exit 1 ;;
esac
