#!/usr/bin/env bash
set -euo pipefail
# ===========================================================================
# checks.sh - run the recette test / gate / report suites
#
# Usage: checks.sh test|gates|report|validate|run|discovery [--docker]
#   default runs locally (.venv); --docker runs inside the lab image.
# ===========================================================================

CICD_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${CICD_DIR}/lib/common.sh"

target="${1:-test}"; shift || true
mode="local"
[ "${1:-}" = "--docker" ] && mode="docker"

run_local() {
    case "${target}" in
        test)      "$(py)" -m unittest discover -s "${REPO_ROOT}/tests" ;;
        gates)     ( cd "${REPO_ROOT}" && make gates ) ;;
        report)    ( cd "${REPO_ROOT}" && "$(py)" -m recette report ) ;;
        validate)  ( cd "${REPO_ROOT}" && "$(py)" -m recette validate ) ;;
        run)       ( cd "${REPO_ROOT}" && "$(py)" -m recette run ) ;;
        discovery) ( cd "${REPO_ROOT}" \
                     && "$(py)" -m recette discovery --adapter reference ) ;;
        *) err "cible inconnue: ${target}"; exit 1 ;;
    esac
}

run_docker() {
    need_docker
    case "${target}" in
        test)  dc run --rm tests ;;
        gates) dc run --rm gates ;;
        run|discovery) dc run --rm recette ;;
        *) err "cible '${target}' indispo en docker (test|gates|run)"; exit 1 ;;
    esac
}

hdr "CHECK ${target} (${mode})"
if [ "${mode}" = "docker" ]; then
    run_docker && ok "${target} OK (docker)"
else
    run_local && ok "${target} OK (local)"
fi
