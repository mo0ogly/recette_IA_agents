#!/usr/bin/env bash
set -euo pipefail
# ===========================================================================
# platform.sh - governed execution platform: lab mock + API + console + campaigns
#
# Usage:
#   platform.sh up|down|restart|status              # lab mock + API, bare-host (dev only, R27)
#   platform.sh up|down|restart|status --docker      # lab-mock + API in Docker (R27 runtime of record)
#   platform.sh up|restart --wire                    # + mitmproxy wire overlay, route wire active au boot
#   platform.sh console start|stop|status|logs
#   platform.sh campaign list
#   platform.sh campaign run <name|file> [--json]
#
# The API started here carries the FULL platform environment (lab URL, event
# store, policies dir), unlike `api.sh start` which runs the bare Track U API.
# Secrets stay in the environment (R8) - never stored here.
#
# --docker drives the compose `api` service (depends_on lab-mock + platform-init,
# see docker-compose.yml) instead of spawning bare-host python processes. Per
# R27 (docker-runtime-mandatory.md) this is the ONLY mode that counts as a live
# proof of the running platform; bare-host stays a fast inner-loop dev check.
# ===========================================================================

CICD_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${CICD_DIR}/lib/common.sh"

API_SH="${CICD_DIR}/api.sh"
WIRE_SH="${CICD_DIR}/wire.sh"
API_PORT_FILE="${RUN_DIR}/api.port"

# Port helpers are shared in lib/common.sh (single source of truth, R19). These
# thin aliases keep the existing call sites working.
_port_free()        { port_free "$@"; }
_kill_port_holder() { kill_port_holder "$@"; }

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

# --- discovery probe replay broker ------------------------------------------

_probe_live_capable() {
    # True iff the privileged live broker can run unprivileged here: the binary
    # exists and carries cap_bpf (granted once via `recette.sh probe-grant-caps`),
    # the eBPF object is built, and a manifest exists. Any missing piece -> replay
    # (fail-safe: never try a live load that would EPERM, never fake one).
    command -v getcap >/dev/null 2>&1 || return 1
    [ -x "${PROBE_LIVE_BROKER}" ] || return 1
    [ -f "${PROBE_BPF_OBJECT}" ] || return 1
    [ -f "${PROBE_MANIFEST}" ] || return 1
    getcap "${PROBE_LIVE_BROKER}" 2>/dev/null | grep -q "cap_bpf" || return 1
    return 0
}

probe_broker_start() {
    # Start the discovery probe broker on the canonical socket. Prefer the
    # PRIVILEGED live eBPF broker when it is capability-granted (one-time
    # `recette.sh probe-grant-caps`); otherwise the NON-privileged replay broker
    # (deterministic corpus replay). The chosen mode is recorded in
    # PROBE_MODE_FILE so the API's /probe/status reports the truth (R13/R14). An
    # operator-set INSPECT_IA_AGENTS_PROBE_SOCKET still wins (handled API-side).
    if _pid_of "${PROBE_PID_FILE}" >/dev/null; then
        warn "probe broker deja en cours (pid $(_pid_of "${PROBE_PID_FILE}"))"
        return 0
    fi
    mkdir -p "${RUN_DIR}"
    case "${PROBE_SOCKET_PATH}" in
        tcp:*) # Free the canonical TCP port before binding (R19). The broker does
               # NOT set SO_REUSEADDR, so a stale holder would make the bind fail;
               # kill it so the fresh broker is the ONLY listener (a Windows
               # SO_REUSEADDR would otherwise let zombies co-bind and answer).
               rm -f "${PROBE_ADDR_FILE}"
               kill_port_holder "${PROBE_SOCKET_PATH##*:}" ;;
        *)     rm -f "${PROBE_SOCKET_PATH}" ;;
    esac
    if _probe_live_capable; then
        # Auto-build the watch-list from EVERY configured agent unless the
        # operator pinned a manifest (INSPECT_IA_AGENTS_PROBE_MANIFEST). So a
        # freshly-created agent is watchable without a manual manifest step.
        local manifest="${PROBE_MANIFEST}"
        if [ -z "${INSPECT_IA_AGENTS_PROBE_MANIFEST:-}" ]; then
            local cfg="${INSPECT_IA_AGENTS_CONFIG_PATH:-${REPO_ROOT}/config/inspect_ia_agents.config.json}"
            if ( cd "${REPO_ROOT}" && "$(py)" -m recette.platform.probe.manifest_gen --from-config "${cfg}" --out "${RUN_DIR}/probe-manifest.json" >/dev/null 2>&1 ); then
                manifest="${RUN_DIR}/probe-manifest.json"
            fi
        fi
        hdr "START probe LIVE eBPF broker (socket ${PROBE_SOCKET_PATH}, mode live, CAP_BPF)"
        ( cd "${REPO_ROOT}" \
            && nohup "${PROBE_LIVE_BROKER}" --socket "${PROBE_SOCKET_PATH}" --manifest "${manifest}" --audit "${PROBE_AUDIT_FILE}" --bpf-object "${PROBE_BPF_OBJECT}" >"${PROBE_LOG_FILE}" 2>&1 & \
            echo $! >"${PROBE_PID_FILE}" )
        printf 'live\n' >"${PROBE_MODE_FILE}"
    else
        hdr "START probe replay broker (socket ${PROBE_SOCKET_PATH}, mode replay)"
        # Seed the watch-list from the SURFACE CORPUS (the subjects the replay
        # broker can replay), so the passive watch (/probe/monitor/start with no
        # agents) has a sensible default in replay/dev mode instead of 400
        # "no agents to watch". An operator-pinned manifest still wins.
        if [ -z "${INSPECT_IA_AGENTS_PROBE_MANIFEST:-}" ]; then
            ( cd "${REPO_ROOT}" && "$(py)" -m recette.platform.probe.manifest_gen --from-surface-corpus --out "${RUN_DIR}/probe-manifest.json" >/dev/null 2>&1 ) || true
        fi
        ( cd "${REPO_ROOT}" \
            && nohup "$(py)" -m recette.platform.probe.replay_broker --socket "${PROBE_SOCKET_PATH}" >"${PROBE_LOG_FILE}" 2>&1 & \
            echo $! >"${PROBE_PID_FILE}" )
        printf 'replay\n' >"${PROBE_MODE_FILE}"
    fi
    # The endpoint appears once the broker has bound; wait briefly. For a
    # tcp:HOST:PORT address (Windows fallback) probe the port with /dev/tcp and
    # record the address in PROBE_ADDR_FILE so the API fallback resolves it.
    local i _ready=0
    case "${PROBE_SOCKET_PATH}" in
        tcp:*)
            local _hp="${PROBE_SOCKET_PATH#tcp:}"
            local _host="${_hp%:*}" _port="${_hp##*:}"
            for ((i = 0; i < 20; i++)); do
                if (exec 3<>"/dev/tcp/${_host}/${_port}") 2>/dev/null; then
                    exec 3>&- 3<&- || true
                    _ready=1
                    break
                fi
                sleep 0.2
            done
            [ "${_ready}" = 1 ] && printf '%s\n' "${PROBE_SOCKET_PATH}" >"${PROBE_ADDR_FILE}"
            ;;
        *)
            for ((i = 0; i < 20; i++)); do
                [ -S "${PROBE_SOCKET_PATH}" ] && { _ready=1; break; }
                sleep 0.2
            done
            ;;
    esac
    if [ "${_ready}" = 1 ]; then
        ok "probe broker pret (${PROBE_SOCKET_PATH}, mode $(cat "${PROBE_MODE_FILE}" 2>/dev/null), pid $(_pid_of "${PROBE_PID_FILE}")) - logs: ${PROBE_LOG_FILE}"
    else
        warn "probe broker endpoint absent - voir ${PROBE_LOG_FILE} (capture restera desactivee)"
    fi
}

probe_broker_stop() {
    local pid _sock_file=""
    case "${PROBE_SOCKET_PATH}" in
        tcp:*) ;;
        *) _sock_file="${PROBE_SOCKET_PATH}" ;;
    esac
    if ! pid="$(_pid_of "${PROBE_PID_FILE}")"; then
        rm -f "${PROBE_PID_FILE}" ${_sock_file:+"${_sock_file}"} "${PROBE_MODE_FILE}" "${PROBE_ADDR_FILE}"
        return 0
    fi
    hdr "STOP probe broker (pid ${pid})"
    kill "${pid}" 2>/dev/null || true
    rm -f "${PROBE_PID_FILE}" ${_sock_file:+"${_sock_file}"} "${PROBE_MODE_FILE}" "${PROBE_ADDR_FILE}"
    ok "probe broker arrete"
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

# --- platform (Docker, R27 -- the governed api/lab-mock run containerized) --

platform_up_docker() {
    need_docker
    hdr "START api + lab-mock (Docker, R27) via docker compose"
    dc up -d api
    if _wait_http "http://127.0.0.1:${API_PORT}/health" 30; then
        ok "plateforme prete (Docker) - API http://127.0.0.1:${API_PORT}"
        dc ps api lab-mock
    else
        err "API (Docker) ne repond pas sur /health"
        dc logs --tail 40 api
        exit 1
    fi
}

platform_down_docker() {
    need_docker
    hdr "STOP api + lab-mock (Docker)"
    dc stop api lab-mock 2>/dev/null || true
    dc rm -f api lab-mock 2>/dev/null || true
    ok "api + lab-mock (Docker) arretes"
}

platform_status_docker() {
    hdr "PLATEFORME GOUVERNEE (Docker)"
    need_docker
    dc ps -a api lab-mock platform-init 2>/dev/null || true
}

platform_wire_up() {
    # Bring up the OPTIONAL mitmproxy wire overlay and select the wire transport
    # route AT BOOT, so the agent <-> server bytes are captured on the wire from
    # the first run -- no manual env + api restart (R19: one launcher wires it).
    #
    # It exports INSPECT_IA_AGENTS_WIRE_PROXY BEFORE the API starts, so
    # recette.platform.proxy.route.registry_from_env() starts active on 'wire'
    # (active_from_env = wire is not None). Then platform_up runs unchanged.
    #
    # Docker-only (mitmproxy runs as a container, R27); a `wire up` failure is
    # fatal here (fail-safe: never claim a wire boot that did not start).
    need_docker
    "${WIRE_SH}" up
    export INSPECT_IA_AGENTS_WIRE_PROXY="http://127.0.0.1:${WIRE_PORT}"
    info "route de transport: wire (mitmproxy) active au boot -> ${INSPECT_IA_AGENTS_WIRE_PROXY}"
    info "HTTPS des systemes reels: faire confiance au CA (./recette.sh wire ca -> INSPECT_IA_AGENTS_WIRE_CA)"
    platform_up
}

platform_up() {
    # Dev convenience: lab domains hot-reload on edit (R5). Exported before
    # lab_start AND before the API start so the :8082 lab and the API-spawned
    # mock_local servers (which inherit the API env) both pick it up. An explicit
    # value wins; the code default stays OFF for tests/replay determinism (I4).
    export INSPECT_IA_AGENTS_LAB_RELOAD="${INSPECT_IA_AGENTS_LAB_RELOAD:-on}"
    lab_start
    # Probe broker: if the operator already points at a privileged (live) broker
    # via INSPECT_IA_AGENTS_PROBE_SOCKET, honour it (mode=live). Otherwise launch
    # the non-privileged replay broker so the Probe view works out of the box.
    if [ -n "${INSPECT_IA_AGENTS_PROBE_SOCKET:-}" ]; then
        export INSPECT_IA_AGENTS_PROBE_MODE="${INSPECT_IA_AGENTS_PROBE_MODE:-live}"
        info "probe broker: socket externe ${INSPECT_IA_AGENTS_PROBE_SOCKET} (mode ${INSPECT_IA_AGENTS_PROBE_MODE})"
    else
        probe_broker_start
        export INSPECT_IA_AGENTS_PROBE_SOCKET="${PROBE_SOCKET_PATH}"
        # Honour the mode the broker ACTUALLY started in (live when CAP_BPF was
        # granted via `recette.sh probe-grant-caps`, replay otherwise). Never
        # force replay over a live broker -- that mismatch made /probe/status lie
        # and forced manual env trafiquer. The launcher alone now wires live
        # end-to-end (R5/R13/R14, R19 single entry point).
        export INSPECT_IA_AGENTS_PROBE_MODE="$(cat "${PROBE_MODE_FILE}" 2>/dev/null || echo replay)"
    fi
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
    probe_broker_stop || true
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
        "recette.platform.probe.replay_broker"
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
    rm -f "${API_PID_FILE}" "${LAB_PID_FILE}" "${CONSOLE_PID_FILE}" "${API_PORT_FILE}" "${PROBE_PID_FILE}"
    rm -f "${PROBE_SOCKET_PATH}"
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
    if pid="$(_pid_of "${PROBE_PID_FILE}")"; then
        ok "probe broker: pid ${pid}, socket ${PROBE_SOCKET_PATH} (mode replay)"
    else
        info "probe broker: arrete"
    fi
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
    # Default: loopback bind + loopback-wired API (local-only, safe). LAN mode
    # (INSPECT_IA_AGENTS_CONSOLE_LAN=1) binds all interfaces and wires the API URL to this
    # host's LAN IP so a remote browser reaches BOTH the console and the API.
    local _vite_host="127.0.0.1" _api_host="${API_HOST}" _lan_ip=""
    if [ "${CONSOLE_LAN}" = "1" ]; then
        _lan_ip="$(lan_ip)"
        if [ -z "${_lan_ip}" ]; then
            err "CONSOLE_LAN=1 but could not detect a LAN IP (lan_ip empty)"; exit 1
        fi
        _vite_host="0.0.0.0"; _api_host="${_lan_ip}"
    fi
    hdr "START console sur ${_vite_host}:${CONSOLE_PORT} (API: http://${_api_host}:${API_PORT})"
    ( cd "${CONSOLE_DIR}" \
        && VITE_INSPECT_IA_AGENTS_API_URL="http://${_api_host}:${API_PORT}" \
           nohup npm run dev -- --host "${_vite_host}" --port "${CONSOLE_PORT}" --strictPort \
           >"${CONSOLE_LOG_FILE}" 2>&1 & \
        echo $! >"${CONSOLE_PID_FILE}" )
    if _wait_http "http://localhost:${CONSOLE_PORT}" 30; then
        if [ -n "${_lan_ip}" ]; then
            ok "console prete (LAN): http://${_lan_ip}:${CONSOLE_PORT}  (API http://${_lan_ip}:${API_PORT})"
            warn "acces distant: l'API doit autoriser l'origine http://${_lan_ip}:${CONSOLE_PORT} dans INSPECT_IA_AGENTS_CORS_ORIGINS (docker compose api)"
        else
            ok "console prete: http://localhost:${CONSOLE_PORT}"
        fi
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
    # accept a bare name (identity-offboarding), a subdir name (banque/sec-1-...),
    # a file name, or an absolute/relative path. Resolves recursively so
    # campaigns nested under campaigns/<group>/ are reachable by short name.
    local name="$1"
    if [ -f "${name}" ]; then echo "${name}"; return 0; fi
    if [ -f "${CAMPAIGNS_DIR}/${name}" ]; then echo "${CAMPAIGNS_DIR}/${name}"; return 0; fi
    if [ -f "${CAMPAIGNS_DIR}/${name}.campaign.json" ]; then
        echo "${CAMPAIGNS_DIR}/${name}.campaign.json"; return 0
    fi
    # recursive fallback: match <name>.campaign.json anywhere under campaigns/
    local hit
    hit="$(find "${CAMPAIGNS_DIR}" -name "${name}.campaign.json" -print -quit 2>/dev/null)"
    if [ -n "${hit}" ]; then echo "${hit}"; return 0; fi
    hit="$(find "${CAMPAIGNS_DIR}" -path "*/${name}" -print -quit 2>/dev/null)"
    if [ -n "${hit}" ]; then echo "${hit}"; return 0; fi
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
        < <(find "${CAMPAIGNS_DIR}" -name '*.campaign.json' | sort)
    if [ "${#files[@]}" -eq 0 ]; then
        warn "aucune campagne dans ${CAMPAIGNS_DIR}"
        return 0
    fi
    hdr "Choisir une campagne (${#files[@]} disponibles)"
    local i rel
    for i in "${!files[@]}"; do
        rel="${files[$i]#"${CAMPAIGNS_DIR}/"}"
        printf "   ${GREEN}%3s)${NC} %s\n" "$((i + 1))" "${rel%.campaign.json}"
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
mode="${1:-}"
case "${cmd}" in
    up)
        case "${mode}" in
            --docker) platform_up_docker ;;
            --wire)   platform_wire_up ;;
            *)        platform_up ;;
        esac ;;
    down)      if [ "${mode}" = "--docker" ]; then platform_down_docker; else platform_down; fi ;;
    restart)
        case "${mode}" in
            --docker) platform_down_docker; platform_up_docker ;;
            --wire)   platform_down; platform_wire_up ;;
            *)        platform_down; platform_up ;;
        esac ;;
    status)    if [ "${mode}" = "--docker" ]; then platform_status_docker; else platform_status; fi ;;
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
    *) err "usage: platform.sh up|down|restart|status [--docker|--wire]|console ...|campaign ..."; exit 1 ;;
esac
