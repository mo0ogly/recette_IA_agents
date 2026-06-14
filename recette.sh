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
#   ./recette.sh platform up|down|restart|status|purge   # lab mock + API gouvernee
#   ./recette.sh console start|stop|status|logs      # UX React (vite dev)
#   ./recette.sh campaign list|run <nom> [--json]    # campagnes d'actions
#   ./recette.sh test|gates|report|validate|run|discovery [--docker]
#   ./recette.sh console-build|console-test    # React console (tsc+vite / vitest)
#   ./recette.sh smoke [--server-port N]               # e2e lab smoke (API + serveur mock + replay)
#   ./recette.sh wire up|down|status|logs              # optional mitmproxy wire-interception overlay (Docker)
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

show_menu() {
    hdr "inspect_ia_agents recette - gestion"
    echo -e "  ${BOLD}Docker lab${NC}"
    echo -e "   ${GREEN}1)${NC} Statut global"
    echo -e "   ${GREEN}2)${NC} Demarrer le lab (up)"
    echo -e "   ${GREEN}3)${NC} Arreter le lab (down)"
    echo -e "   ${GREEN}4)${NC} Redemarrer le lab"
    echo -e "   ${GREEN}5)${NC} Rebuild image"
    echo -e "   ${GREEN}6)${NC} Logs lab"
    echo -e "  ${BOLD}API Track U${NC}"
    echo -e "   ${GREEN}7)${NC} API start"
    echo -e "   ${GREEN}8)${NC} API stop"
    echo -e "   ${GREEN}9)${NC} API statut"
    echo -e "  ${BOLD}Checks${NC}"
    echo -e "  ${GREEN}10)${NC} Tests (local)"
    echo -e "  ${GREEN}11)${NC} Gates (local)"
    echo -e "  ${GREEN}12)${NC} Report (local)"
    echo -e "  ${GREEN}13)${NC} Tests (docker)"
    echo -e "  ${BOLD}Git${NC}"
    echo -e "  ${GREEN}14)${NC} Git statut"
    echo -e "  ${GREEN}15)${NC} Git pull"
    echo -e "  ${GREEN}16)${NC} Git push"
    echo -e "  ${GREEN}17)${NC} Git sync (fetch + etat)"
    echo -e "  ${BOLD}Plateforme gouvernee${NC}"
    echo -e "  ${GREEN}18)${NC} Plateforme up (lab mock + API)"
    echo -e "  ${GREEN}19)${NC} Plateforme down"
    echo -e "  ${GREEN}20)${NC} Plateforme statut"
    echo -e "  ${GREEN}21)${NC} Console UX start (http://localhost:${CONSOLE_PORT})"
    echo -e "  ${GREEN}22)${NC} Console UX stop"
    echo -e "  ${BOLD}Campagnes${NC}"
    echo -e "  ${GREEN}23)${NC} Lister les campagnes"
    echo -e "  ${GREEN}24)${NC} Lancer une campagne"
    echo -e "  ${BOLD}Nettoyage${NC}"
    echo -e "  ${GREEN}25)${NC} Purger les serveurs web locaux (API, lab, console)"
    echo
    echo -e "   ${GREEN}0)${NC} Quitter"
    echo
    echo -n "  Choix : "
}

menu_loop() {
    while true; do
        show_menu
        local c; read -r c
        case "${c}" in
            1)  "${STATUS_SH}" ;;
            2)  "${DOCKER_SH}" up ;;
            3)  "${DOCKER_SH}" down ;;
            4)  "${DOCKER_SH}" restart ;;
            5)  "${DOCKER_SH}" rebuild ;;
            6)  "${DOCKER_SH}" logs ;;
            7)  "${API_SH}" start ;;
            8)  "${API_SH}" stop ;;
            9)  "${API_SH}" status ;;
            10) "${CHECKS_SH}" test ;;
            11) "${CHECKS_SH}" gates ;;
            12) "${CHECKS_SH}" report ;;
            13) "${CHECKS_SH}" test --docker ;;
            14) "${GIT_SH}" status ;;
            15) "${GIT_SH}" pull ;;
            16) "${GIT_SH}" push ;;
            17) "${GIT_SH}" sync ;;
            18) "${PLATFORM_SH}" up ;;
            19) "${PLATFORM_SH}" down ;;
            20) "${PLATFORM_SH}" status ;;
            21) "${PLATFORM_SH}" console start ;;
            22) "${PLATFORM_SH}" console stop ;;
            23) "${PLATFORM_SH}" campaign list ;;
            24) "${PLATFORM_SH}" campaign menu ;;
            25) "${PLATFORM_SH}" purge ;;
            0|q|Q) info "Bye"; exit 0 ;;
            *)  warn "choix invalide" ;;
        esac
        echo; read -rp "  Entree pour continuer..." _
    done
}

cmd="${1:-menu}"; shift || true
case "${cmd}" in
    menu)                              menu_loop ;;
    up|down|restart|rebuild|ps|logs|shell)
                                       "${DOCKER_SH}" "${cmd}" "$@" ;;
    status)                            "${STATUS_SH}" ;;
    api)                               "${API_SH}" "$@" ;;
    platform)                          "${PLATFORM_SH}" "$@" ;;
    console)                           "${PLATFORM_SH}" console "$@" ;;
    campaign)                          "${PLATFORM_SH}" campaign "$@" ;;
    test|gates|report|validate|run|discovery|console-build|console-test)
                                       "${CHECKS_SH}" "${cmd}" "$@" ;;
    smoke)                             "${SMOKE_SH}" "$@" ;;
    wire)                              "${WIRE_SH}" "$@" ;;
    git)                               "${GIT_SH}" "$@" ;;
    -h|--help|help)
        sed -n '4,20p' "${ROOT}/recette.sh" | sed 's/^# \{0,1\}//' ;;
    *)  err "commande inconnue: ${cmd}"; \
        echo "  voir: ./recette.sh --help"; exit 1 ;;
esac
