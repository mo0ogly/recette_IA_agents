#!/usr/bin/env bash
set -euo pipefail
# ===========================================================================
# docker.sh - manage the recette Docker lab (build / up / down / restart)
#
# Usage: docker.sh up|down|restart|rebuild|ps|logs [svc]|shell [svc]
# ===========================================================================

CICD_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${CICD_DIR}/lib/common.sh"

action="${1:-ps}"; shift || true

case "${action}" in
    build|rebuild)
        need_docker
        hdr "BUILD lab image"
        dc build && ok "image construite"
        ;;
    up)
        need_docker
        hdr "UP discovery-mock (lab)"
        # only the long-running service needs `up`; runners are one-shot
        dc up -d discovery-mock && ok "discovery-mock demarre"
        ;;
    down)
        need_docker
        hdr "DOWN lab"
        dc down && ok "lab arrete"
        ;;
    restart)
        need_docker
        hdr "RESTART lab"
        dc down
        dc up -d discovery-mock && ok "lab redemarre"
        ;;
    ps)
        need_docker
        hdr "Conteneurs lab"
        dc ps
        ;;
    logs)
        need_docker
        svc="${1:-discovery-mock}"
        hdr "Logs ${svc} (Ctrl-C pour quitter)"
        dc logs -f "${svc}"
        ;;
    shell)
        need_docker
        svc="${1:-discovery-mock}"
        hdr "Shell dans ${svc}"
        dc exec "${svc}" /bin/sh || dc run --rm "${svc}" /bin/sh
        ;;
    *)
        err "action inconnue: ${action}"
        echo "  up|down|restart|rebuild|ps|logs [svc]|shell [svc]"
        exit 1
        ;;
esac
