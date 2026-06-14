#!/usr/bin/env bash
# install_python_audit.sh -- Install the Python quality/security tooling used by
# /python-recette and cmd/python_recette. inspect_ia_agents's Python counterpart to
# install_rust_audit.sh.
#
# Installs into a dedicated project virtualenv (.venv-pyaudit) to avoid PEP 668
# "externally-managed-environment" failures and stay reproducible:
#   - ruff       (lint + format, includes flake8-bandit S security rules)  -> go vet + gofmt + part of gosec
#   - mypy       (static type checking)
#   - bandit     (deep security SAST)                                       -> gosec
#   - pip-audit  (vulnerable dependency scan via OSV / PyPI advisory)       -> govulncheck
#   - pytest     (test runner)                                              -> go test
#
# Idempotent. Safe to re-run.
#
# Usage:
#   scripts/install_python_audit.sh           # create venv + install everything
#   scripts/install_python_audit.sh --check   # report status only, install nothing
#
# Reference: .claude/commands/python-recette.md

set -euo pipefail

MODE="${1:-install}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${REPO_ROOT}/.venv-pyaudit"
BIN="${VENV}/bin"

info()  { printf '[INFO]  %s\n' "$*"; }
ok()    { printf '[OK]    %s\n' "$*"; }
warn()  { printf '[WARN]  %s\n' "$*" >&2; }
err()   { printf '[ERROR] %s\n' "$*" >&2; }

# Tools pinned-by-floor; pip resolves the latest compatible at install time.
TOOLS=(ruff mypy bandit pip-audit pytest types-jsonschema)

report() {
  printf '\n%-12s %s\n' "TOOL" "STATUS"
  printf '%-12s %s\n'   "----" "------"
  local t path
  for t in "${TOOLS[@]}"; do
    path="${BIN}/${t}"
    if [ -x "$path" ]; then
      printf '%-12s INSTALLED (%s)\n' "$t" "$("$path" --version 2>&1 | head -1)"
    elif command -v "$t" >/dev/null 2>&1; then
      printf '%-12s INSTALLED on PATH (%s)\n' "$t" "$("$t" --version 2>&1 | head -1)"
    else
      printf '%-12s absent\n' "$t"
    fi
  done
  printf '\nvenv: %s\n' "$VENV"
}

if [ "$MODE" = "--check" ]; then
  info "Checking Python audit tooling status (no install)."
  report
  exit 0
fi

# --- 1. python3 present? --------------------------------------------------
if ! command -v python3 >/dev/null 2>&1; then
  err "python3 not found. Install Python 3.11+ first."
  exit 1
fi
info "Using $(python3 --version 2>&1)."

# --- 2. create the dedicated venv ----------------------------------------
if [ ! -d "$VENV" ]; then
  info "Creating virtualenv at ${VENV}."
  python3 -m venv "$VENV"
  ok "virtualenv created."
else
  ok "virtualenv already present."
fi

# --- 3. upgrade pip + install tools --------------------------------------
info "Upgrading pip."
"${BIN}/python" -m pip install --quiet --upgrade pip

info "Installing: ${TOOLS[*]}"
if "${BIN}/python" -m pip install --quiet --upgrade "${TOOLS[@]}"; then
  ok "tools installed."
else
  warn "one or more tools failed to install -- /python-recette will mark their bloc N/A."
fi

# --- 4. report ------------------------------------------------------------
report
ok "Done. Activate with: source ${VENV}/bin/activate  (or call ${BIN}/<tool> directly)."
ok "Run '/python-recette <path>' or 'python -m python_recette <path>' to validate Python code."
