#!/usr/bin/env bash
set -euo pipefail
# ===========================================================================
# smoke.sh - e2e lab smoke test (API liveness + smoke_lab.py)
#
# Usage: smoke.sh [--server-port N] [extra args passed to smoke_lab.py]
# Starts the API if not already running, then runs scripts/smoke_lab.py.
# Exit 0 = SMOKE PASS, exit 1 = fail.
# ===========================================================================

CICD_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${CICD_DIR}/lib/common.sh"

API_SH="${CICD_DIR}/api.sh"

# -- wait for the API to be reachable, starting it if needed ----------------
_health_url="http://${API_HOST}:${API_PORT}/health"

if ! curl -fsS "${_health_url}" >/dev/null 2>&1; then
    info "API not reachable at ${_health_url} - starting it"
    "${API_SH}" start

    _retries=20
    _up=0
    for _i in $(seq 1 "${_retries}"); do
        if curl -fsS "${_health_url}" >/dev/null 2>&1; then
            _up=1
            break
        fi
        sleep 0.5
    done

    if [ "${_up}" -eq 0 ]; then
        err "API did not become reachable after ${_retries} attempts (${_health_url})"
        exit 1
    fi
fi

ok "API up at ${_health_url}"

# -- run smoke ---------------------------------------------------------------
hdr "SMOKE e2e lab"
# set -e would abort before _rc is captured on failure, swallowing the FAIL
# message: guard the call so the code is reported, then propagated by exit.
_rc=0
"$(py)" "${REPO_ROOT}/scripts/smoke_lab.py" --api "http://${API_HOST}:${API_PORT}" "$@" || _rc=$?

if [ "${_rc}" -eq 0 ]; then
    ok "SMOKE PASS"
else
    err "SMOKE FAIL (exit ${_rc})"
fi

exit "${_rc}"
