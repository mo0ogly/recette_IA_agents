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

# Optional browser smoke: `smoke.sh --console` also drives the React console in
# a real Chromium (scripts/smoke_console.py) after the lab + chaos smokes. The
# flag is extracted here so the remaining args still pass through to smoke_lab.
RUN_CONSOLE=0
_passthrough=()
for _arg in "$@"; do
    if [ "${_arg}" = "--console" ]; then
        RUN_CONSOLE=1
    else
        _passthrough+=("${_arg}")
    fi
done
set -- "${_passthrough[@]+"${_passthrough[@]}"}"

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

# Chaos fail-safe smoke (A1): self-contained (spins its own mock server), proves
# the governed proxy surfaces an INFRA fault instead of fabricating success.
# Independent of the API, so it runs even if the lab smoke above had issues.
hdr "SMOKE chaos fail-safe"
_rc_chaos=0
"$(py)" "${REPO_ROOT}/scripts/smoke_chaos.py" || _rc_chaos=$?
[ "${_rc_chaos}" -eq 0 ] && ok "CHAOS SMOKE PASS" || err "CHAOS SMOKE FAIL (exit ${_rc_chaos})"
[ "${_rc}" -eq 0 ] && _rc="${_rc_chaos}"

# Browser console smoke (opt-in via --console): requires a running console
# (vite) on CONSOLE_PORT pointed at this API. Skipped-with-warning if down,
# so the default lab smoke stays self-contained.
if [ "${RUN_CONSOLE}" -eq 1 ]; then
    hdr "SMOKE browser console"
    _console_url="http://localhost:${CONSOLE_PORT}"
    if curl -fsS "${_console_url}" >/dev/null 2>&1; then
        _rc_console=0
        "$(py)" "${REPO_ROOT}/scripts/smoke_console.py" \
            --console "${_console_url}" --api "http://${API_HOST}:${API_PORT}" || _rc_console=$?
        [ "${_rc_console}" -eq 0 ] && ok "CONSOLE SMOKE PASS" || err "CONSOLE SMOKE FAIL (exit ${_rc_console})"
        [ "${_rc}" -eq 0 ] && _rc="${_rc_console}"
    else
        err "console not reachable at ${_console_url} -- run './recette.sh console start' first (skipped)"
    fi
fi

if [ "${_rc}" -eq 0 ]; then
    ok "SMOKE PASS"
else
    err "SMOKE FAIL (exit ${_rc})"
fi

exit "${_rc}"
