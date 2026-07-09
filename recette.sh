#!/usr/bin/env bash
set -euo pipefail
# ===========================================================================
# recette.sh - single entry point to manage the inspect_ia_agents recette platform
#
# Interactive menu:
#   ./recette.sh
#
# CLI (non-interactive) - delegates to the cicd/ sub-programs:
#   ./recette.sh up|down|restart|rebuild|ps     # docker lab
#   ./recette.sh logs [svc]|shell [svc]         # docker lab
#   ./recette.sh status                         # full snapshot
#   ./recette.sh api start|stop|restart|status|logs
#   ./recette.sh all up|down|restart                     # TOUT d'un coup: plateforme + wire overlay + console UX
#   ./recette.sh platform up|down|restart|status|purge   # lab mock + API gouvernee
#   ./recette.sh platform up --docker                    # plateforme gouvernee en Docker (R27 runtime de reference)
#   ./recette.sh platform up --wire                      # + overlay mitmproxy, route wire active au boot (capture bytes)
#   ./recette.sh console start|stop|status|logs      # UX React (vite dev)
#   ./recette.sh campaign list|run <nom> [--json]    # campagnes d'actions
#   ./recette.sh test|gates|report|validate|run|discovery|recette-full [--docker]
#   ./recette.sh console-build|console-test    # React console (tsc+vite / vitest)
#   ./recette.sh discovery-build               # native Rust discovery engines (cargo, discoveryprobe/)
#   ./recette.sh probe-ebpf-build              # build the eBPF object + CAP_BPF broker (live capture; see docs/runbooks/ebpf-live-capture.md)
#   ./recette.sh probe-grant-caps              # ONE-TIME: grant CAP_BPF to the broker (sudo) so platform up runs it live
#   ./recette.sh docs-build|docs-serve         # Docusaurus doc site build / serve fr+en (docs-site/)
#   ./recette.sh smoke [--server-port N]               # e2e lab smoke (API + serveur mock + replay)
#   ./recette.sh wire up|down|status|logs|ca           # optional mitmproxy wire-interception overlay (Docker)
#   ./recette.sh llm-proxy up|down|status|logs         # optional LiteLLM LLM-gateway overlay (Docker)
#   ./recette.sh git status|pull|push|sync|branches|clean-merged
#
# Auteur : Fabrice Pizzi - ANSSI
# ===========================================================================

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CICD_DIR="${ROOT}/cicd"
source "${CICD_DIR}/lib/common.sh"

DOCKER_SH="${CICD_DIR}/docker.sh"
API_SH="${CICD_DIR}/api.sh"
STATUS_SH="${CICD_DIR}/status.sh"
CHECKS_SH="${CICD_DIR}/checks.sh"
GIT_SH="${CICD_DIR}/git.sh"
PLATFORM_SH="${CICD_DIR}/platform.sh"
SMOKE_SH="${CICD_DIR}/smoke.sh"
WIRE_SH="${CICD_DIR}/wire.sh"
LLM_PROXY_SH="${CICD_DIR}/llm_proxy.sh"

# --- submenu helpers ---------------------------------------------------------
# _pause: wait for the operator after an action ran inside a submenu.
_pause() { echo; read -rp "  Entree pour continuer..." _; }

# _opt: render one numbered submenu option.
_opt() { printf "  ${GREEN}%2s)${NC} %s\n" "$1" "$2"; }

show_main_menu() {
    hdr "inspect_ia_agents recette - gestion"
    _opt 1 "Services        (lab + API + console UX + statut)"
    _opt 2 "Recette         (validate / run / discovery / smoke / campagnes / gates)"
    _opt 3 "Build           (console / docs / rust-discovery / ebpf)"
    _opt 4 "Git"
    _opt 5 "Proxy overlays  (Docker, optionnel)"
    _opt 6 "Cleanup"
    echo
    _opt 0 "Quitter"
    echo
    echo -n "  Choix : "
}

submenu_docker() {
    while true; do
        hdr "Docker lab"
        _opt 1 "Statut global"
        _opt 2 "Demarrer le lab (up)"
        _opt 3 "Arreter le lab (down)"
        _opt 4 "Redemarrer le lab"
        _opt 5 "Rebuild image"
        _opt 6 "Logs lab"
        _opt 7 "ps (conteneurs)"
        _opt 8 "shell (conteneur)"
        echo; _opt 0 "Retour"; echo -n "  Choix : "
        local c; read -r c
        case "${c}" in
            1) "${STATUS_SH}"; _pause ;;
            2) "${DOCKER_SH}" up; _pause ;;
            3) "${DOCKER_SH}" down; _pause ;;
            4) "${DOCKER_SH}" restart; _pause ;;
            5) "${DOCKER_SH}" rebuild; _pause ;;
            6) "${DOCKER_SH}" logs; _pause ;;
            7) "${DOCKER_SH}" ps; _pause ;;
            8) "${DOCKER_SH}" shell; _pause ;;
            0|q|Q) return ;;
            *) warn "choix invalide"; _pause ;;
        esac
    done
}

submenu_api() {
    while true; do
        hdr "API gouvernee"
        _opt 1 "API start"
        _opt 2 "API stop"
        _opt 3 "API restart"
        _opt 4 "API statut"
        _opt 5 "API logs"
        echo; _opt 0 "Retour"; echo -n "  Choix : "
        local c; read -r c
        case "${c}" in
            1) "${API_SH}" start; _pause ;;
            2) "${API_SH}" stop; _pause ;;
            3) "${API_SH}" restart; _pause ;;
            4) "${API_SH}" status; _pause ;;
            5) "${API_SH}" logs; _pause ;;
            0|q|Q) return ;;
            *) warn "choix invalide"; _pause ;;
        esac
    done
}

submenu_git() {
    while true; do
        hdr "Git"
        _opt 1 "Git statut"
        _opt 2 "Git pull"
        _opt 3 "Git push"
        _opt 4 "Git sync (fetch + etat)"
        echo; _opt 0 "Retour"; echo -n "  Choix : "
        local c; read -r c
        case "${c}" in
            1) "${GIT_SH}" status; _pause ;;
            2) "${GIT_SH}" pull; _pause ;;
            3) "${GIT_SH}" push; _pause ;;
            4) "${GIT_SH}" sync; _pause ;;
            0|q|Q) return ;;
            *) warn "choix invalide"; _pause ;;
        esac
    done
}

submenu_services() {
    while true; do
        hdr "Services (plateforme gouvernee + console UX)"
        _opt 1 "TOUT demarrer (lab + API + wire + console)"
        _opt 2 "TOUT arreter"
        _opt 3 "TOUT redemarrer"
        echo
        _opt 4 "Statut global"
        _opt 5 "Plateforme up (lab mock + API)"
        _opt 6 "Plateforme down"
        _opt 7 "Plateforme restart"
        _opt 8 "Console UX start (http://localhost:${CONSOLE_PORT})"
        _opt 9 "Console UX stop"
        _opt 10 "Console UX statut"
        _opt 11 "Console UX logs"
        echo
        _opt 12 "Docker lab (sous-menu)"
        _opt 13 "API gouvernee (sous-menu)"
        echo; _opt 0 "Retour"; echo -n "  Choix : "
        local c; read -r c
        case "${c}" in
            1) all_up; _pause ;;
            2) all_down; _pause ;;
            3) all_restart; _pause ;;
            4) "${STATUS_SH}"; _pause ;;
            5) "${PLATFORM_SH}" up; _pause ;;
            6) "${PLATFORM_SH}" down; _pause ;;
            7) "${PLATFORM_SH}" restart; _pause ;;
            8) "${PLATFORM_SH}" console start; _pause ;;
            9) "${PLATFORM_SH}" console stop; _pause ;;
            10) "${PLATFORM_SH}" console status; _pause ;;
            11) "${PLATFORM_SH}" console logs; _pause ;;
            12) submenu_docker ;;
            13) submenu_api ;;
            0|q|Q) return ;;
            *) warn "choix invalide"; _pause ;;
        esac
    done
}

submenu_campaign() {
    while true; do
        hdr "Campagnes"
        _opt 1 "Lister les campagnes"
        _opt 2 "Lancer une campagne"
        echo; _opt 0 "Retour"; echo -n "  Choix : "
        local c; read -r c
        case "${c}" in
            1) "${PLATFORM_SH}" campaign list; _pause ;;
            2) "${PLATFORM_SH}" campaign menu; _pause ;;
            0|q|Q) return ;;
            *) warn "choix invalide"; _pause ;;
        esac
    done
}

submenu_recette() {
    while true; do
        hdr "Recette & Discovery"
        _opt 1 "Validate (schema corpus + repos)"
        _opt 2 "Run identification (scorecard 4 dimensions)"
        _opt 3 "Discovery (adapter reference)"
        _opt 4 "Smoke e2e (API + lab mock + replay)"
        _opt 5 "Campagnes (sous-menu)"
        _opt 6 "Recette full (sweep deterministe + RETEX)"
        echo
        _opt 7 "Tests (unittest, local)"
        _opt 8 "Gates (ruff / mypy / bandit)"
        _opt 9 "Report (scorecard agrege)"
        _opt 10 "Tests (docker)"
        echo; _opt 0 "Retour"; echo -n "  Choix : "
        local c; read -r c
        case "${c}" in
            1) "${CHECKS_SH}" validate; _pause ;;
            2) "${CHECKS_SH}" run; _pause ;;
            3) "${CHECKS_SH}" discovery; _pause ;;
            4) "${SMOKE_SH}"; _pause ;;
            5) submenu_campaign ;;
            6) "${CHECKS_SH}" recette-full; _pause ;;
            7) "${CHECKS_SH}" test; _pause ;;
            8) "${CHECKS_SH}" gates; _pause ;;
            9) "${CHECKS_SH}" report; _pause ;;
            10) "${CHECKS_SH}" test --docker; _pause ;;
            0|q|Q) return ;;
            *) warn "choix invalide"; _pause ;;
        esac
    done
}

submenu_proxy() {
    while true; do
        hdr "Proxy overlays (Docker, optionnel)"
        _opt 1 "Wire interception (mitmproxy) up"
        _opt 2 "Wire interception down"
        _opt 3 "Wire interception statut"
        _opt 4 "Wire interception logs"
        _opt 5 "LLM-proxy (LiteLLM) up"
        _opt 6 "LLM-proxy down"
        _opt 7 "LLM-proxy statut"
        _opt 8 "LLM-proxy logs"
        echo; _opt 0 "Retour"; echo -n "  Choix : "
        local c; read -r c
        case "${c}" in
            1) "${WIRE_SH}" up; _pause ;;
            2) "${WIRE_SH}" down; _pause ;;
            3) "${WIRE_SH}" status; _pause ;;
            4) "${WIRE_SH}" logs; _pause ;;
            5) "${LLM_PROXY_SH}" up; _pause ;;
            6) "${LLM_PROXY_SH}" down; _pause ;;
            7) "${LLM_PROXY_SH}" status; _pause ;;
            8) "${LLM_PROXY_SH}" logs; _pause ;;
            0|q|Q) return ;;
            *) warn "choix invalide"; _pause ;;
        esac
    done
}

submenu_build() {
    while true; do
        hdr "Build (console / docs / natifs)"
        _opt 1 "Console build (tsc + vite)"
        _opt 2 "Console test (vitest)"
        _opt 3 "Docs build (Docusaurus fr+en)"
        _opt 4 "Docs serve"
        echo
        _opt 5 "Moteurs Rust discovery (cargo)"
        _opt 6 "Sonde eBPF + broker CAP_BPF"
        _opt 7 "Grant CAP_BPF au broker (sudo, one-time)"
        echo; _opt 0 "Retour"; echo -n "  Choix : "
        local c; read -r c
        case "${c}" in
            1) "${CHECKS_SH}" console-build; _pause ;;
            2) "${CHECKS_SH}" console-test; _pause ;;
            3) "${CHECKS_SH}" docs-build; _pause ;;
            4) "${CHECKS_SH}" docs-serve; _pause ;;
            5) "${CHECKS_SH}" discovery-build; _pause ;;
            6) "${CHECKS_SH}" probe-ebpf-build; _pause ;;
            7) "${CHECKS_SH}" probe-grant-caps; _pause ;;
            0|q|Q) return ;;
            *) warn "choix invalide"; _pause ;;
        esac
    done
}

submenu_cleanup() {
    while true; do
        hdr "Nettoyage"
        _opt 1 "Purger les serveurs web locaux (API, lab, console)"
        echo; _opt 0 "Retour"; echo -n "  Choix : "
        local c; read -r c
        case "${c}" in
            1) "${PLATFORM_SH}" purge; _pause ;;
            0|q|Q) return ;;
            *) warn "choix invalide"; _pause ;;
        esac
    done
}

# --- one-shot "everything" orchestration -------------------------------------
# all_up: bring up, in one command, everything needed to OBSERVE agents -- the
# governed platform (lab mock + API) with the mitmproxy wire overlay active at
# boot (so the wire panel is populated with zero manual enable dance), plus the
# console UX. Composes only verified sub-verbs (platform up --wire, console
# start). Bare-host dev path: mitmproxy itself still runs in Docker via wire.sh;
# for the Docker runtime of record use `platform up --docker` (R27).
all_up() {
    hdr "TOUT demarrer (plateforme + wire overlay + console)"
    "${PLATFORM_SH}" up --wire
    "${PLATFORM_SH}" console start
    ok "tout est demarre -- console: http://localhost:${CONSOLE_PORT}"
}

# all_down: stop everything all_up started, in reverse order (console, then the
# platform, then the wire overlay). Best-effort per step so an already-stopped
# component never aborts the teardown (set -e safe via || true).
all_down() {
    hdr "TOUT arreter (console + plateforme + wire overlay)"
    "${PLATFORM_SH}" console stop || true
    "${PLATFORM_SH}" down || true
    # wire.sh down prints two advisories about unsetting INSPECT_IA_AGENTS_WIRE_PROXY
    # and restarting the API to return to direct transport. They are moot in a full
    # teardown -- all_down stops the API right after, so nothing is left pointing at
    # the proxy. Drop just those two lines (both carry the env-var marker) without
    # touching wire.sh (R19 single implementation); keep the header/OK and any error.
    local wire_out
    wire_out="$("${WIRE_SH}" down 2>&1)" || true
    printf '%s\n' "${wire_out}" | grep -v "INSPECT_IA_AGENTS_WIRE_PROXY" || true
    ok "tout est arrete"
}

# all_restart: full down then full up (down is best-effort, up is strict).
all_restart() {
    all_down
    all_up
}

menu_loop() {
    while true; do
        show_main_menu
        local c; read -r c
        case "${c}" in
            1)  submenu_services ;;
            2)  submenu_recette ;;
            3)  submenu_build ;;
            4)  submenu_git ;;
            5)  submenu_proxy ;;
            6)  submenu_cleanup ;;
            0|q|Q) info "Bye"; exit 0 ;;
            *)  warn "choix invalide"; _pause ;;
        esac
    done
}

cmd="${1:-menu}"; shift || true
case "${cmd}" in
    menu)                              menu_loop ;;
    all)
        case "${1:-up}" in
            up)      all_up ;;
            down)    all_down ;;
            restart) all_restart ;;
            *) err "usage: ./recette.sh all up|down|restart"; exit 1 ;;
        esac ;;
    up|down|restart|rebuild|ps|logs|shell)
                                       "${DOCKER_SH}" "${cmd}" "$@" ;;
    status)                            "${STATUS_SH}" ;;
    api)                               "${API_SH}" "$@" ;;
    platform)                          "${PLATFORM_SH}" "$@" ;;
    console)                           "${PLATFORM_SH}" console "$@" ;;
    campaign)                          "${PLATFORM_SH}" campaign "$@" ;;
    test|gates|report|validate|run|discovery|recette-full|discovery-build|probe-ebpf-build|probe-grant-caps|console-build|console-test|docs-build|docs-serve)
                                       "${CHECKS_SH}" "${cmd}" "$@" ;;
    smoke)                             "${SMOKE_SH}" "$@" ;;
    wire)                              "${WIRE_SH}" "$@" ;;
    llm-proxy)                         "${LLM_PROXY_SH}" "$@" ;;
    git)                               "${GIT_SH}" "$@" ;;
    -h|--help|help)
        sed -n '4,23p' "${ROOT}/recette.sh" | sed 's/^# \{0,1\}//' ;;
    *)  err "commande inconnue: ${cmd}"; \
        echo "  voir: ./recette.sh --help"; exit 1 ;;
esac
