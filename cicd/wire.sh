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
# Usage: wire.sh up|down|status|logs|ca
#
#   up      start the mitmproxy container (host network, binds :${WIRE_PORT})
#   down    stop and remove the container
#   status  show whether the overlay container is running
#   logs    tail the mitmproxy logs
#   ca      print the path to the mitmproxy CA (to trust for HTTPS interception)
#
# After `up`, route agents through it (HTTP lab targets):
#   export INSPECT_IA_AGENTS_WIRE_PROXY=http://127.0.0.1:${WIRE_PORT}
#   ./recette.sh api restart
#
# To intercept HTTPS to real systems (real_saas: slack via StdlibHttpClient,
# github/gitlab via SDK), also trust the mitmproxy CA:
#   export INSPECT_IA_AGENTS_WIRE_CA="$(./recette.sh wire ca)"
#   # SDK forges (PyGithub/python-gitlab) honour the standard env instead:
#   export HTTPS_PROXY=http://127.0.0.1:${WIRE_PORT} REQUESTS_CA_BUNDLE="$(./recette.sh wire ca)"
#   ./recette.sh api restart
# ===========================================================================

CICD_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${CICD_DIR}/lib/common.sh"

action="${1:-status}"; shift || true

case "${action}" in
    up)
        need_docker
        hdr "UP wire overlay (mitmproxy) sur :${WIRE_PORT}"
        mkdir -p "${RUN_DIR}/mitmproxy"
        dc --profile wire up -d wire-proxy && ok "wire-proxy demarre"
        info "Pour router les agents au travers (cibles HTTP):"
        info "  export INSPECT_IA_AGENTS_WIRE_PROXY=http://127.0.0.1:${WIRE_PORT}"
        info "Pour le HTTPS des systemes reels, ajouter le CA:"
        info "  export INSPECT_IA_AGENTS_WIRE_CA=\"\$(./recette.sh wire ca)\""
        info "Puis: ./recette.sh api restart"
        ;;
    ca)
        # Print the mitmproxy CA path so it can be trusted (INSPECT_IA_AGENTS_WIRE_CA /
        # REQUESTS_CA_BUNDLE). It appears after the first `wire up` generates it.
        ca_path="${RUN_DIR}/mitmproxy/mitmproxy-ca-cert.pem"
        if [ ! -f "${ca_path}" ]; then
            err "CA absent (${ca_path}). Lancer d'abord: ./recette.sh wire up"
            exit 1
        fi
        echo "${ca_path}"
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
        echo "  voir: ./recette.sh wire up|down|status|logs|ca"
        exit 1
        ;;
esac
