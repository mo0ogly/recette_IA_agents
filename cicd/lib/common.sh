#!/usr/bin/env bash
# ===========================================================================
# common.sh - shared helpers for the recette management scripts
#
# Source with:
#   CICD_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
#   source "${CICD_DIR}/lib/common.sh"
#
# Auteur : Fabrice Pizzi - ANSSI
# ===========================================================================

# -- repo root (cicd/lib/common.sh -> repo root is two levels up) -----------
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# -- ANSI colours -----------------------------------------------------------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; GRAY='\033[0;90m'
BOLD='\033[1m'; NC='\033[0m'

# -- log helpers ------------------------------------------------------------
ok()   { echo -e "${GREEN}[OK]${NC} $1"; }
info() { echo -e "${BLUE}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[ATTENTION]${NC} $1"; }
err()  { echo -e "${RED}[ERREUR]${NC} $1" >&2; }
sep()  { echo -e "${GRAY}$(printf '%.0s-' {1..68})${NC}"; }
hdr()  { echo -e "\n${CYAN}== $1 ==${NC}"; }

# -- API server defaults (Track U / U1) -------------------------------------
API_HOST="${AGENTRAIL_API_HOST:-127.0.0.1}"
API_PORT="${AGENTRAIL_API_PORT:-8090}"
RUN_DIR="${REPO_ROOT}/.run"
API_PID_FILE="${RUN_DIR}/api.pid"
API_LOG_FILE="${RUN_DIR}/api.log"

# -- python picker: prefer the project venv, else system python3 ------------
py() {
    if [ -x "${REPO_ROOT}/.venv/bin/python" ]; then
        echo "${REPO_ROOT}/.venv/bin/python"
    else
        echo "python3"
    fi
}

# -- docker compose wrapper (runs from the repo root) -----------------------
dc() {
    ( cd "${REPO_ROOT}" && docker compose "$@" )
}

# -- guards -----------------------------------------------------------------
need_docker() {
    command -v docker >/dev/null 2>&1 || { err "docker introuvable"; exit 1; }
    docker version >/dev/null 2>&1 || { err "daemon docker KO"; exit 1; }
}

confirm() {
    # confirm "question" -> 0 if user answers o/O/y/Y
    local q="${1:-Confirmer ?}"
    echo -n "  ${q} [o/N] : "
    local r; read -r r
    [[ "${r}" =~ ^[oOyY]$ ]]
}
