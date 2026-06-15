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
    # Free the canonical port before binding: an orphan recette.api (not tracked
    # in api.pid) squatting ${API_PORT} would make the new process answer with
    # stale code. The port is enforced, never relocated (R19).
    kill_port_holder "${API_PORT}"
    hdr "START API sur ${API_HOST}:${API_PORT}"
    ( cd "${REPO_ROOT}" \
        && INSPECT_IA_AGENTS_API_HOST="${API_HOST}" \
           INSPECT_IA_AGENTS_API_PORT="${API_PORT}" \
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
    if pid="$(_api_pid)"; then
        hdr "STOP API (pid ${pid})"
        kill "${pid}" 2>/dev/null || true
        sleep 1
        kill -0 "${pid}" 2>/dev/null && kill -9 "${pid}" 2>/dev/null || true
    else
        info "API non demarree (pid file absent)"
    fi
    # Always free the canonical port: kill any orphan holding ${API_PORT} that is
    # not tracked in api.pid, so a following start binds fresh code (R19).
    kill_port_holder "${API_PORT}"
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
