#!/usr/bin/env bash
# rust-recette-deep-scan.sh -- Bloc D orchestration for /rust-recette
# Runs the full Rust static-analysis gate (clippy + audit + fmt + deny + geiger),
# the AgentRail equivalent of go-recette-deep-scan.sh (gosec + govulncheck).
#
# Usage: .claude/scripts/rust-recette-deep-scan.sh [file_or_crate_dir]
#   - With no arg: scans the whole workspace.
#   - With a path: used only to derive `-p <crate>` when inside a crate; the cargo
#     tools are workspace-aware and scan the resolved package(s).
#
# Outputs (under /tmp/rust-recette-deep/):
#   clippy.txt   audit.txt / audit.json   fmt.txt   deny.txt   geiger.txt   report.md
#
# Exit code: 0 if no CRITICAL gate failed (clippy -D warnings clean AND no RUSTSEC
# HIGH/CRITICAL), 1 otherwise. N/A tools never fail the run (reported as N/A).
#
# Reference: .claude/commands/rust-recette.md Bloc D

set -u
TARGET="${1:-}"
OUT=/tmp/rust-recette-deep
mkdir -p "$OUT"

have() { command -v "$1" >/dev/null 2>&1; }

# Source cargo env if present (rustup default install location).
[ -f "${HOME}/.cargo/env" ] && # shellcheck disable=SC1091
  . "${HOME}/.cargo/env" 2>/dev/null || true

# Derive an optional -p <crate> selector from the target path, when it sits in a crate.
PKG_ARG=()
if [ -n "$TARGET" ]; then
  dir="$TARGET"; [ -f "$TARGET" ] && dir="$(dirname "$TARGET")"
  while [ "$dir" != "/" ] && [ "$dir" != "." ]; do
    if [ -f "$dir/Cargo.toml" ] && ! grep -q '^\[workspace\]' "$dir/Cargo.toml" 2>/dev/null; then
      name="$(grep -m1 '^name\s*=' "$dir/Cargo.toml" 2>/dev/null | sed -E 's/.*"([^"]+)".*/\1/')"
      [ -n "$name" ] && PKG_ARG=(-p "$name")
      break
    fi
    dir="$(dirname "$dir")"
  done
fi

CRIT_FAIL=0

if ! have cargo; then
  printf '[ERROR] cargo absent -- run scripts/install_rust_audit.sh first.\n' >&2
  exit 1
fi

# --- D1 clippy ------------------------------------------------------------
printf '[D1] cargo clippy -D warnings ...\n'
if cargo clippy "${PKG_ARG[@]}" --all-targets --all-features -- -D warnings >"$OUT/clippy.txt" 2>&1; then
  D1="PASS"
else
  D1="FAIL"; CRIT_FAIL=1
fi
CLIPPY_WARN=$(grep -cE '^warning' "$OUT/clippy.txt" 2>/dev/null) || true; CLIPPY_WARN=${CLIPPY_WARN:-0}
CLIPPY_ERR=$(grep -cE '^error' "$OUT/clippy.txt" 2>/dev/null) || true; CLIPPY_ERR=${CLIPPY_ERR:-0}

# --- D2 cargo audit (RustSec) --------------------------------------------
if have cargo-audit; then
  printf '[D2] cargo audit ...\n'
  cargo audit >"$OUT/audit.txt" 2>&1 || true
  cargo audit --json >"$OUT/audit.json" 2>/dev/null || true
  AUDIT_HC=$(grep -cE 'Severity: (high|critical)' "$OUT/audit.txt" 2>/dev/null) || true; AUDIT_HC=${AUDIT_HC:-0}
  if [ "$AUDIT_HC" -gt 0 ]; then D2="FAIL"; CRIT_FAIL=1; else D2="PASS"; fi
else
  D2="N/A"; AUDIT_HC="n/a"
fi

# --- D3 cargo fmt ---------------------------------------------------------
printf '[D3] cargo fmt --check ...\n'
if cargo fmt --all -- --check >"$OUT/fmt.txt" 2>&1; then D3="PASS"; else D3="FAIL"; fi

# --- D4 cargo deny --------------------------------------------------------
if have cargo-deny; then
  printf '[D4] cargo deny check ...\n'
  if cargo deny check advisories bans licenses sources >"$OUT/deny.txt" 2>&1; then
    D4="PASS"
  else
    D4="FAIL"
  fi
else
  D4="N/A"
fi

# --- D5 cargo geiger ------------------------------------------------------
if have cargo-geiger; then
  printf '[D5] cargo geiger ...\n'
  cargo geiger "${PKG_ARG[@]}" --output-format Ascii >"$OUT/geiger.txt" 2>&1 || true
  D5="see report"
else
  D5="N/A"
fi

# --- consolidated report --------------------------------------------------
{
  printf 'RUST RECETTE DEEP SCAN\n'
  printf 'Target  : %s\n' "${TARGET:-<workspace>}"
  printf 'Package : %s\n' "${PKG_ARG[*]:-<all>}"
  printf '======================================\n\n'
  printf 'D1 cargo clippy : %s (warnings=%s errors=%s)\n' "$D1" "$CLIPPY_WARN" "$CLIPPY_ERR"
  printf 'D2 cargo audit  : %s (HIGH/CRIT=%s)\n' "$D2" "$AUDIT_HC"
  printf 'D3 cargo fmt    : %s\n' "$D3"
  printf 'D4 cargo deny   : %s\n' "$D4"
  printf 'D5 cargo geiger : %s\n' "$D5"
  printf '\nFull logs in %s/\n' "$OUT"
  if [ "$CRIT_FAIL" -eq 0 ]; then
    printf '\nVERDICT: no CRITICAL static-analysis gate failed.\n'
  else
    printf '\nVERDICT: CRITICAL FAIL (clippy and/or RUSTSEC HIGH/CRITICAL). See logs.\n'
  fi
} | tee "$OUT/report.md"

exit "$CRIT_FAIL"
