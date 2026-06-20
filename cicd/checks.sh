#!/usr/bin/env bash
set -euo pipefail
# ===========================================================================
# checks.sh - run the recette test / gate / report suites
#
# Usage: checks.sh test|gates|report|validate|run|discovery [--docker]
#        checks.sh console-build|console-test          (React console, local only)
#        checks.sh docs-build|docs-serve                (Docusaurus doc site, local only)
#   default runs locally (.venv); --docker runs inside the lab image.
# ===========================================================================

CICD_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${CICD_DIR}/lib/common.sh"

target="${1:-test}"; shift || true
mode="local"
[ "${1:-}" = "--docker" ] && mode="docker"

run_local() {
    case "${target}" in
        test)      # Isolate the config path: the suite runs against a throwaway
                   # COPY of the corpus so no test can ever write the tracked
                   # config/inspect_ia_agents.config.json (R20 anti-pollution).
                   # Reads see identical content; writes land in the copy.
                   _cfgdir="$(mktemp -d)"
                   cp "${REPO_ROOT}/config/inspect_ia_agents.config.json" \
                      "${_cfgdir}/inspect_ia_agents.config.json"
                   INSPECT_IA_AGENTS_CONFIG_PATH="${_cfgdir}/inspect_ia_agents.config.json" \
                       "$(py)" -m unittest discover -s "${REPO_ROOT}/tests"
                   rm -rf "${_cfgdir}" ;;
        gates)     ( cd "${REPO_ROOT}" && make gates ) ;;
        report)    ( cd "${REPO_ROOT}" && "$(py)" -m recette report ) ;;
        validate)  ( cd "${REPO_ROOT}" && "$(py)" -m recette validate ) ;;
        run)       ( cd "${REPO_ROOT}" && "$(py)" -m recette run ) ;;
        discovery) ( cd "${REPO_ROOT}" \
                     && "$(py)" -m recette discovery --adapter reference ) ;;
        discovery-build) # Build the native Rust discovery engines (host workspace;
                         # the discoveryprobe-ebpf crate is excluded -- different
                         # target). Produces target/release/discoveryprobe-catalog,
                         # the binary GET /catalog/rust-summary invokes.
                         ( cd "${REPO_ROOT}/discoveryprobe" \
                           && { [ -f "${HOME}/.cargo/env" ] && . "${HOME}/.cargo/env"; } \
                           && cargo build --release ) ;;
        probe-ebpf-build) # Build the PRIVILEGED live-capture pieces: the eBPF
                         # object (nightly + bpf-linker, bpfel target) and the
                         # CAP_BPF broker. Loading them needs CAP_BPF at runtime
                         # (see docs/runbooks/ebpf-live-capture.md); this only
                         # BUILDS, never loads (no privilege required to compile).
                         ( cd "${REPO_ROOT}/discoveryprobe" \
                           && { [ -f "${HOME}/.cargo/env" ] && . "${HOME}/.cargo/env"; } \
                           && ( cd discoveryprobe-ebpf && cargo build --release ) \
                           && cargo build --release -p discoveryprobe-broker \
                           && ls -l discoveryprobe-ebpf/target/bpfel-unknown-none/release/discoveryprobe-trace \
                                    target/release/discoveryprobe-broker ) ;;
        console-build) ( cd "${REPO_ROOT}/console" \
                         && node node_modules/.bin/tsc --noEmit \
                         && node node_modules/.bin/vite build ) ;;
        console-test)  ( cd "${REPO_ROOT}/console" \
                         && node node_modules/.bin/vitest run ) ;;
        docs-build)    ( cd "${REPO_ROOT}/docs-site" \
                         && { [ -d node_modules ] || npm ci; } \
                         && npm run build ) ;;
        docs-serve)    ( cd "${REPO_ROOT}/docs-site" \
                         && { [ -d build/en ] || npm run build; } \
                         && npm run serve -- --port 3000 --host 0.0.0.0 ) ;;
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
