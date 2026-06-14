#!/usr/bin/env bash
set -euo pipefail
# ===========================================================================
# wire.sh - manage the OPTIONAL mitmproxy wire-interception overlay (Docker)
#
# The overlay is a real HTTP(S) interception proxy (mitmproxy) that captures the
# bytes on the wire of the agent -> target-system traffic and POSTs each flow to
# the API wire ring (POST /proxy/wire), surfaced on the console Proxy page.
#
# It is OFF by default (compose profile "wire") and a SURCHARGE, never a
# replacement: the deterministic recette never routes through it. It runs as a
# Docker container (no fork/subprocess from the API, R19).
#
# Usage: wire.sh up|down|status|logs
#
#   up      start the mitmproxy container (host network, binds :${WIRE_PORT})
#   down    stop and remove the container
#   status  show whether the overlay container is running
#   logs    tail the mitmproxy logs
#
# After `up`, route agents through it:
#   export INSPECT_IA_AGENTS_WIRE_PROXY=http://127.0.0.1:${WIRE_PORT}
#   ./recette.sh api restart
# ===========================================================================

CICD_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${CICD_DIR}/lib/common.sh"

action="${1:-status}"; shift || true

case "${action}" in
    up)
        need_docker
        hdr "UP wire overlay (mitmproxy) sur :${WIRE_PORT}"
        dc --profile wire up -d wire-proxy && ok "wire-proxy demarre"
        info "Pour router les agents au travers:"
        info "  export INSPECT_IA_AGENTS_WIRE_PROXY=http://127.0.0.1:${WIRE_PORT}"
        info "  ./recette.sh api restart"
        ;;
    down)
        need_docker
        hdr "DOWN wire overlay"
        dc --profile wire rm -sf wire-proxy && ok "wire-proxy arrete"
        warn "Les agents continuent de pointer le proxy tant que INSPECT_IA_AGENTS_WIRE_PROXY est set."
        warn "Pour revenir au direct: unset INSPECT_IA_AGENTS_WIRE_PROXY puis ./recette.sh api restart."
        ;;
    status)
        need_docker
        hdr "Etat wire overlay"
        dc --profile wire ps wire-proxy
        ;;
    logs)
        need_docker
        dc --profile wire logs --tail "${1:-100}" wire-proxy
        ;;
    *)
        err "action wire inconnue: ${action}"
        echo "  voir: ./recette.sh wire up|down|status|logs"
        exit 1
        ;;
esac
