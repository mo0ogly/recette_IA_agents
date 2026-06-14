#!/usr/bin/env bash
set -euo pipefail
# ===========================================================================
# llm_proxy.sh - manage the OPTIONAL LiteLLM gateway overlay (Docker)
#
# An OpenAI-compatible gateway that centralizes and observes the agents' LLM
# calls (the "brain" view; the wire overlay covers the "hands"/target traffic).
# OFF by default (compose profile "llm"), a SURCHARGE, never a replacement: the
# deterministic recette uses StubLlm/ReplayLlm and never calls a real model.
# Runs as a Docker container (no fork/subprocess from the API, R19).
#
# Usage: llm_proxy.sh up|down|status|logs
#
# After `up`, point an inspect_ia_agents ai_backend at it:
#   provider = openai_compat
#   base_url = http://127.0.0.1:${LLM_PROXY_PORT}
#   model    = one of the model_name entries in config/litellm.config.yaml
#   api_key  = the LITELLM_MASTER_KEY (default sk-recette-local)
# Provider keys live in .env (R18); they are forwarded into the container.
# ===========================================================================

CICD_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${CICD_DIR}/lib/common.sh"

action="${1:-status}"; shift || true

case "${action}" in
    up)
        need_docker
        hdr "UP LLM gateway (LiteLLM) sur :${LLM_PROXY_PORT}"
        dc --profile llm up -d llm-proxy && ok "llm-proxy demarre"
        info "Configurer un ai_backend: provider=openai_compat,"
        info "  base_url=http://127.0.0.1:${LLM_PROXY_PORT}, model=<model_name de config/litellm.config.yaml>"
        info "  api_key=\${LITELLM_MASTER_KEY:-sk-recette-local}"
        ;;
    down)
        need_docker
        hdr "DOWN LLM gateway"
        dc --profile llm rm -sf llm-proxy && ok "llm-proxy arrete"
        ;;
    status)
        need_docker
        hdr "Etat LLM gateway"
        dc --profile llm ps llm-proxy
        ;;
    logs)
        need_docker
        dc --profile llm logs --tail "${1:-100}" llm-proxy
        ;;
    *)
        err "action llm-proxy inconnue: ${action}"
        echo "  voir: ./recette.sh llm-proxy up|down|status|logs"
        exit 1
        ;;
esac
