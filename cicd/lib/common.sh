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

# -- Port helpers (shared by api.sh + platform.sh) --------------------------
# Policy (R19): the canonical port is enforced, never relocated. If a port is
# held -- even by an orphan not tracked in any .run/*.pid -- the holder is
# killed so the service binds where it is expected.
port_free() {
    ! ss -ltn 2>/dev/null | awk '{print $4}' | grep -q ":${1}\$"
}
kill_port_holder() {
    local port="$1" pids
    # `|| true`: when the port is FREE, grep finds nothing and exits 1; under the
    # callers' `set -euo pipefail` an unguarded substitution would abort. We want
    # "free port" to be a clean no-op, so swallow the empty-match failure.
    pids="$(ss -ltnp 2>/dev/null | awk -v p=":${port}" '$4 ~ p"$"' \
        | grep -oP 'pid=\K[0-9]+' | sort -u | tr '\n' ' ' || true)"
    [ -z "${pids// /}" ] && return 0
    warn "port ${port} occupe par pid(s) ${pids}- kill (port canonique impose R19)"
    # shellcheck disable=SC2086
    kill ${pids} 2>/dev/null || true
    sleep 1
    if ! port_free "${port}"; then
        # shellcheck disable=SC2086
        kill -9 ${pids} 2>/dev/null || true
        sleep 1
    fi
}

# -- API server defaults (Track U / U1) -------------------------------------
API_HOST="${INSPECT_IA_AGENTS_API_HOST:-127.0.0.1}"
API_PORT="${INSPECT_IA_AGENTS_API_PORT:-8090}"
RUN_DIR="${REPO_ROOT}/.run"
API_PID_FILE="${RUN_DIR}/api.pid"
API_LOG_FILE="${RUN_DIR}/api.log"

# -- governed platform defaults (lab mock + persistent stores, R5 via env) --
LAB_PORT="${INSPECT_IA_AGENTS_LAB_PORT:-8091}"
LAB_PID_FILE="${RUN_DIR}/lab.pid"
LAB_LOG_FILE="${RUN_DIR}/lab.log"
PLATFORM_DATA_DIR="${INSPECT_IA_AGENTS_PLATFORM_DATA:-${REPO_ROOT}/data}"
EVENT_STORE_PATH="${INSPECT_IA_AGENTS_EVENT_STORE_PATH:-${PLATFORM_DATA_DIR}/inspect_ia_agents.events.db}"
POLICIES_DIR="${INSPECT_IA_AGENTS_POLICIES_DIR:-${REPO_ROOT}/config/policies}"

# -- console (React dev server) ----------------------------------------------
CONSOLE_DIR="${REPO_ROOT}/console"
CONSOLE_PORT="${INSPECT_IA_AGENTS_CONSOLE_PORT:-5174}"
CONSOLE_PID_FILE="${RUN_DIR}/console.pid"
CONSOLE_LOG_FILE="${RUN_DIR}/console.log"
# LAN exposure (opt-in, off by default for safety). INSPECT_IA_AGENTS_CONSOLE_LAN=1
# makes `console start` bind vite on all interfaces AND wire the console to the
# API via this host's LAN IP (so a remote browser's API calls resolve to this
# host, not its own loopback). The API must also allow the resulting origin in
# CORS (docker compose api INSPECT_IA_AGENTS_CORS_ORIGINS, see docker-compose.yml).
CONSOLE_LAN="${INSPECT_IA_AGENTS_CONSOLE_LAN:-0}"

# lan_ip -- best-effort primary LAN IPv4 of this host (the source address the
# default route would use), for advertising a reachable console/API URL.
lan_ip() {
    ip route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}'
}

# -- campaigns ---------------------------------------------------------------
CAMPAIGNS_DIR="${REPO_ROOT}/campaigns"
CAMPAIGN_REPORTS_DIR="${RUN_DIR}/campaigns"

# -- wire proxy (optional mitmproxy interception overlay, Docker) ------------
# The host port mitmdump binds; agents route through http://127.0.0.1:${WIRE_PORT}
# when INSPECT_IA_AGENTS_WIRE_PROXY points at it. Off unless the operator brings it up.
WIRE_PORT="${INSPECT_IA_AGENTS_WIRE_PORT:-8092}"

# -- LLM gateway (optional LiteLLM overlay, Docker) --------------------------
# The host port the LiteLLM proxy binds; an ai_backend (openai_compat) targets
# http://127.0.0.1:${LLM_PROXY_PORT}. Off unless the operator brings it up.
LLM_PROXY_PORT="${INSPECT_IA_AGENTS_LLM_PROXY_PORT:-9093}"

# -- discovery probe broker (Unix socket) ------------------------------------
# The console Probe view relays a capture to a broker on this socket. In dev/CI
# (no CAP_BPF) the non-privileged REPLAY broker is launched here, serving a
# deterministic replay of the corpus surface ground-truth (mode=replay). The
# privileged eBPF broker would set mode=live. Socket path lives under .run/.
PROBE_SOCKET_PATH="${INSPECT_IA_AGENTS_PROBE_SOCKET:-${RUN_DIR}/probe.sock}"
PROBE_PID_FILE="${RUN_DIR}/probe.pid"
PROBE_LOG_FILE="${RUN_DIR}/probe.log"
# The launcher records here which broker it started (live|replay) so the API's
# /probe/status reports the truth for the canonical socket (R13/R14).
PROBE_MODE_FILE="${RUN_DIR}/probe.mode"
# The CAP_BPF live broker + its eBPF object (built by `recette.sh probe-ebpf-build`)
# and the agents allowlist manifest. The live broker is used ONLY when the binary
# carries cap_bpf (one-time `recette.sh probe-grant-caps`); otherwise replay.
PROBE_LIVE_BROKER="${REPO_ROOT}/discoveryprobe/target/release/discoveryprobe-broker"
PROBE_BPF_OBJECT="${REPO_ROOT}/discoveryprobe/discoveryprobe-ebpf/target/bpfel-unknown-none/release/discoveryprobe-trace"
PROBE_MANIFEST="${INSPECT_IA_AGENTS_PROBE_MANIFEST:-${REPO_ROOT}/discoveryprobe/discoveryprobe-broker/manifest.example.json}"
PROBE_AUDIT_FILE="${RUN_DIR}/probe.audit.jsonl"

# -- python picker: prefer the project venv, else system python3 ------------
# Checks both venv layouts: bin/ (Linux/macOS) and Scripts/ (Windows Git Bash,
# used by recette.ps1 which delegates here).
py() {
    if [ -x "${REPO_ROOT}/.venv/bin/python" ]; then
        echo "${REPO_ROOT}/.venv/bin/python"
    elif [ -x "${REPO_ROOT}/.venv/Scripts/python.exe" ]; then
        echo "${REPO_ROOT}/.venv/Scripts/python.exe"
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
