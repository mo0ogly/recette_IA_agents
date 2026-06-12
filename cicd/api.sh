#!/usr/bin/env bash
set -euo pipefail
# ===========================================================================
# api.sh - manage the Track U / U1 API server (uvicorn, recette.api)
#
# Usage: api.sh start|stop|restart|status|logs
# The server runs in the background; pid + logs live under .run/.
# Keys/secrets come from the environment (R8) - never stored here.
# ===========================================================================

CICD_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${CICD_DIR}/lib/common.sh"

_api_pid() {
    [ -f "${API_PID_FILE}" ] || return 1
    local pid; pid="$(cat "${API_PID_FILE}" 2>/dev/null || true)"
    [ -n "${pid}" ] && kill -0 "${pid}" 2>/dev/null || return 1
    echo "${pid}"
}

api_start() {
    if _api_pid >/dev/null; then
        warn "API deja en cours (pid $(_api_pid))"
        return 0
    fi
    mkdir -p "${RUN_DIR}"
    hdr "START API sur ${API_HOST}:${API_PORT}"
    ( cd "${REPO_ROOT}" \
        && AGENTRAIL_API_HOST="${API_HOST}" \
           AGENTRAIL_API_PORT="${API_PORT}" \
           nohup "$(py)" -m recette.api >"${API_LOG_FILE}" 2>&1 & \
        echo $! >"${API_PID_FILE}" )
    sleep 1
    if _api_pid >/dev/null; then
        ok "API demarree (pid $(_api_pid)) - logs: ${API_LOG_FILE}"
    else
        err "API n'a pas demarre - voir ${API_LOG_FILE}"
        tail -n 20 "${API_LOG_FILE}" 2>/dev/null || true
        exit 1
    fi
}

api_stop() {
    local pid
    if ! pid="$(_api_pid)"; then
        info "API non demarree"
        rm -f "${API_PID_FILE}"
        return 0
    fi
    hdr "STOP API (pid ${pid})"
    kill "${pid}" 2>/dev/null || true
    sleep 1
    kill -0 "${pid}" 2>/dev/null && kill -9 "${pid}" 2>/dev/null || true
    rm -f "${API_PID_FILE}"
    ok "API arretee"
}

api_status() {
    hdr "Statut API"
    if _api_pid >/dev/null; then
        ok "en cours (pid $(_api_pid)) sur ${API_HOST}:${API_PORT}"
        local url="http://${API_HOST}:${API_PORT}/health"
        if command -v curl >/dev/null 2>&1; then
            echo -n "  /health : "; curl -s "${url}" || echo "(injoignable)"
            echo
        fi
    else
        warn "arretee"
    fi
}

action="${1:-status}"
case "${action}" in
    start)   api_start ;;
    stop)    api_stop ;;
    restart) api_stop; api_start ;;
    status)  api_status ;;
    logs)    tail -f "${API_LOG_FILE}" ;;
    *) err "action inconnue: ${action}"; \
       echo "  start|stop|restart|status|logs"; exit 1 ;;
esac
