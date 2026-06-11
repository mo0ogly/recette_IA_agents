#!/usr/bin/env bash
# install.sh -- Install the AgentRail recette platform end-to-end.
#
# Sets up a native runnable environment (a project virtualenv with the recette
# package installed editable) AND, when Docker is available, builds + verifies the
# discovery lab images. Every step is verified by a smoke test -- the script does not
# claim success without running the recette (validate + offline discovery + tests).
#
# Native env lives in .venv (recette runtime + dev tooling). The audit gates keep
# using .venv-pyaudit (see install_python_audit.sh); this script bootstraps it too.
#
# Usage:
#   scripts/install.sh                 native install + docker lab build/verify
#   scripts/install.sh --no-docker     native install only (skip Docker)
#   scripts/install.sh --with-real     also install the [real] extras (PyGithub, python-gitlab)
#   scripts/install.sh --check         report status only, install nothing
#   scripts/install.sh --help
#
# Idempotent. Safe to re-run.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${REPO_ROOT}/.venv"
BIN="${VENV}/bin"
PY_MIN_MAJOR=3
PY_MIN_MINOR=11

DO_DOCKER=1
WITH_REAL=0
MODE=install

info()  { printf '[INFO]  %s\n' "$*"; }
ok()    { printf '[OK]    %s\n' "$*"; }
warn()  { printf '[WARN]  %s\n' "$*" >&2; }
err()   { printf '[ERROR] %s\n' "$*" >&2; }
step()  { printf '\n==== %s ====\n' "$*"; }

usage() {
  sed -n '2,24p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  exit 0
}

for arg in "$@"; do
  case "$arg" in
    --no-docker) DO_DOCKER=0 ;;
    --with-real) WITH_REAL=1 ;;
    --check)     MODE=check ;;
    --help|-h)   usage ;;
    *) err "unknown argument: ${arg}"; usage ;;
  esac
done

# --- prerequisite: python >= 3.11 -----------------------------------------
require_python() {
  if ! command -v python3 >/dev/null 2>&1; then
    err "python3 not found. Install Python ${PY_MIN_MAJOR}.${PY_MIN_MINOR}+ first."
    exit 1
  fi
  local maj min
  maj="$(python3 -c 'import sys; print(sys.version_info[0])')"
  min="$(python3 -c 'import sys; print(sys.version_info[1])')"
  if [ "$maj" -lt "$PY_MIN_MAJOR" ] || { [ "$maj" -eq "$PY_MIN_MAJOR" ] && [ "$min" -lt "$PY_MIN_MINOR" ]; }; then
    err "Python ${maj}.${min} is too old; need ${PY_MIN_MAJOR}.${PY_MIN_MINOR}+ (StrEnum, modern typing)."
    exit 1
  fi
  info "Using $(python3 --version 2>&1)."
}

docker_ready() {
  command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1
}

# --- --check : report only -------------------------------------------------
report_status() {
  step "STATUS"
  if [ -x "${BIN}/recette" ]; then
    ok "native venv: ${VENV} (recette installed)"
  elif [ -d "$VENV" ]; then
    warn "native venv exists but recette not installed: ${VENV}"
  else
    warn "native venv absent: ${VENV}"
  fi
  if [ -x "${REPO_ROOT}/.venv-pyaudit/bin/ruff" ]; then
    ok "audit venv: ${REPO_ROOT}/.venv-pyaudit"
  else
    warn "audit venv absent (run scripts/install_python_audit.sh for native gates)"
  fi
  if docker_ready; then
    ok "docker: $(docker --version 2>&1 | head -1)"
    docker image inspect railgun-recette:runtime >/dev/null 2>&1 && ok "image railgun-recette:runtime present" || warn "image railgun-recette:runtime absent"
    docker image inspect railgun-recette:audit   >/dev/null 2>&1 && ok "image railgun-recette:audit present"   || warn "image railgun-recette:audit absent"
  else
    warn "docker (with compose v2) not available"
  fi
}

if [ "$MODE" = check ]; then
  report_status
  exit 0
fi

# --- native install --------------------------------------------------------
require_python

step "NATIVE ENV (${VENV})"
if [ ! -d "$VENV" ]; then
  info "Creating virtualenv."
  python3 -m venv "$VENV"
  ok "virtualenv created."
else
  ok "virtualenv already present."
fi

info "Upgrading pip."
"${BIN}/python" -m pip install --quiet --upgrade pip

EXTRA_SPEC="dev"
if [ "$WITH_REAL" -eq 1 ]; then
  EXTRA_SPEC="dev,real"
  info "Including [real] extras (PyGithub, python-gitlab)."
fi
info "Installing recette (editable) with extras: [${EXTRA_SPEC}]"
"${BIN}/python" -m pip install --quiet --upgrade -e "${REPO_ROOT}[${EXTRA_SPEC}]"
ok "recette installed editable in ${VENV}."

# --- audit env (for native gates + pre-commit hook) -----------------------
step "AUDIT ENV (.venv-pyaudit)"
if [ -x "${REPO_ROOT}/scripts/install_python_audit.sh" ]; then
  "${REPO_ROOT}/scripts/install_python_audit.sh" >/dev/null 2>&1 && ok "audit tooling ready (.venv-pyaudit)." || warn "audit tooling install reported issues; native gates may be partial."
else
  warn "scripts/install_python_audit.sh missing; skipping audit env."
fi

# --- native smoke tests (R14: verify, do not assume) ----------------------
step "NATIVE SMOKE"
NATIVE_OK=1

info "recette validate"
if "${BIN}/recette" validate; then ok "corpus schema-valid."; else err "validate FAILED."; NATIVE_OK=0; fi

info "recette discovery --adapter reference"
if "${BIN}/recette" discovery --adapter reference | tee /tmp/recette_discovery.out | grep -q "VERDICT: PASS"; then
  ok "offline discovery recette: VERDICT PASS."
else
  err "offline discovery recette did NOT report VERDICT PASS."; NATIVE_OK=0
fi

info "unittest suite"
if "${BIN}/python" -m unittest discover -s "${REPO_ROOT}/tests" >/tmp/recette_tests.out 2>&1; then
  ok "tests: $(tail -1 /tmp/recette_tests.out)"
else
  err "tests FAILED:"; tail -5 /tmp/recette_tests.out >&2; NATIVE_OK=0
fi

# --- docker lab build + verify --------------------------------------------
DOCKER_OK="skipped"
if [ "$DO_DOCKER" -eq 1 ]; then
  if docker_ready; then
    step "DOCKER LAB (build + verify)"
    DOCKER_OK=1
    info "Building images (runtime + audit)."
    if (cd "$REPO_ROOT" && docker compose build); then ok "images built."; else err "docker build FAILED."; DOCKER_OK=0; fi

    if [ "$DOCKER_OK" -eq 1 ]; then
      info "tests in container"
      (cd "$REPO_ROOT" && docker compose run --rm tests) && ok "container tests OK." || { err "container tests FAILED."; DOCKER_OK=0; }

      info "strict gates in container"
      (cd "$REPO_ROOT" && docker compose run --rm gates) && ok "container gates PASS." || { err "container gates FAILED."; DOCKER_OK=0; }

      info "discovery recette over HTTP (vs mock :8081)"
      (cd "$REPO_ROOT" && docker compose run --rm recette) && ok "HTTP discovery recette PASS." || { err "HTTP discovery recette FAILED."; DOCKER_OK=0; }

      info "tearing down lab"
      (cd "$REPO_ROOT" && docker compose down --remove-orphans) >/dev/null 2>&1 || true
    fi
  else
    warn "Docker (with compose v2) not available -- skipping the lab. Re-run after installing Docker, or use --no-docker to silence this."
    DOCKER_OK="unavailable"
  fi
else
  info "Docker step skipped (--no-docker)."
fi

# --- final report ----------------------------------------------------------
step "SUMMARY"
case "$DOCKER_OK" in
  1) DOCKER_LABEL=OK ;;
  0) DOCKER_LABEL=FAILED ;;
  *) DOCKER_LABEL="$DOCKER_OK" ;;
esac
printf '  native env   : %s\n' "$([ "$NATIVE_OK" -eq 1 ] && echo 'OK' || echo 'FAILED')"
printf '  docker lab   : %s\n' "$DOCKER_LABEL"
printf '\n'
printf 'Run the recette:\n'
printf '  source %s/bin/activate\n' "$VENV"
printf '  recette validate            # schema-validate the corpus\n'
printf '  recette run                 # identification scorecard\n'
printf '  recette discovery --adapter reference   # offline discovery scorecard\n'
printf '  make lab                    # discovery recette over HTTP in Docker\n'

if [ "$NATIVE_OK" -ne 1 ] || [ "$DOCKER_OK" = 0 ]; then
  err "Installation completed WITH failures (see above)."
  exit 1
fi
ok "Installation complete and verified."
