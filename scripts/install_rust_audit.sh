#!/usr/bin/env bash
# install_rust_audit.sh -- Install the Rust toolchain + audit/SAST tooling used by /rust-recette.
#
# This is the AgentRail (Railgun) equivalent of what gosec/govulncheck/golangci-lint
# provided for the Go /go-recette pipeline. It installs:
#   - rustup + stable toolchain (rustc, cargo)        (if absent)
#   - clippy + rustfmt components                     (go vet / gofmt equivalents)
#   - cargo-audit    (RUSTSEC advisory DB scan)       (govulncheck equivalent)
#   - cargo-deny     (advisories + bans + licenses + sources policy)
#   - cargo-geiger   (unsafe code surface)            (part of gosec equivalent)
#   - cargo-nextest  (faster test runner)             (go test equivalent)
#   - cargo-llvm-cov (test coverage)                  (go test -cover equivalent)
#
# Idempotent: re-running skips already-installed tools. Safe to run in CI.
#
# Usage:
#   scripts/install_rust_audit.sh            # install everything missing
#   scripts/install_rust_audit.sh --check    # report status only, install nothing
#   scripts/install_rust_audit.sh --minimal  # toolchain + clippy/rustfmt + cargo-audit only
#
# Reference: .claude/commands/rust-recette.md (the recette this tooling backs).

set -euo pipefail

MODE="${1:-install}"

# --- output helpers (no emoji, R10) ---------------------------------------
info()  { printf '[INFO]  %s\n' "$*"; }
ok()    { printf '[OK]    %s\n' "$*"; }
warn()  { printf '[WARN]  %s\n' "$*" >&2; }
err()   { printf '[ERROR] %s\n' "$*" >&2; }

have()  { command -v "$1" >/dev/null 2>&1; }

# Source cargo env if rustup installed it in this shell session already.
[ -f "${HOME}/.cargo/env" ] && # shellcheck disable=SC1091
  . "${HOME}/.cargo/env" 2>/dev/null || true

# --- status report --------------------------------------------------------
report() {
  printf '\n%-16s %s\n' "TOOL" "STATUS"
  printf '%-16s %s\n'   "----" "------"
  local t
  for t in rustup rustc cargo cargo-clippy rustfmt cargo-audit cargo-deny \
           cargo-geiger cargo-nextest cargo-llvm-cov; do
    if have "$t"; then
      printf '%-16s INSTALLED (%s)\n' "$t" "$("$t" --version 2>/dev/null | head -1)"
    else
      printf '%-16s absent\n' "$t"
    fi
  done
  printf '\n'
}

if [ "$MODE" = "--check" ]; then
  info "Checking Rust audit tooling status (no install)."
  report
  exit 0
fi

# --- 1. rustup + stable toolchain -----------------------------------------
if ! have rustup; then
  info "rustup absent -- installing the official toolchain (stable)."
  if ! have curl; then
    err "curl is required to bootstrap rustup. Install curl and re-run."
    exit 1
  fi
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain stable
  # shellcheck disable=SC1091
  . "${HOME}/.cargo/env"
  ok "rustup + stable toolchain installed."
else
  ok "rustup present ($(rustup --version 2>/dev/null | head -1))."
  rustup toolchain install stable --no-self-update >/dev/null 2>&1 || true
fi

# --- 2. clippy + rustfmt components (go vet / gofmt equivalents) ----------
info "Ensuring clippy + rustfmt components."
rustup component add clippy rustfmt >/dev/null 2>&1 || warn "could not add clippy/rustfmt components."
have cargo-clippy && ok "clippy ready." || warn "clippy still missing."
have rustfmt      && ok "rustfmt ready." || warn "rustfmt still missing."

# --- 3. cargo-installed audit tools ---------------------------------------
# cargo-binstall fetches prebuilt binaries when available (much faster than
# compiling from source); fall back to `cargo install` otherwise.
CARGO_INSTALL=(cargo install --locked)
if have cargo-binstall; then
  info "cargo-binstall detected -- using prebuilt binaries where possible."
  CARGO_INSTALL=(cargo binstall --no-confirm)
fi

install_crate() {
  local bin="$1" crate="$2"
  if have "$bin"; then
    ok "$bin already installed ($("$bin" --version 2>/dev/null | head -1))."
    return 0
  fi
  info "Installing $crate ..."
  if "${CARGO_INSTALL[@]}" "$crate"; then
    ok "$crate installed."
  else
    warn "failed to install $crate -- /rust-recette will mark its bloc as N/A (tool missing)."
  fi
}

# cargo-audit is the non-negotiable RUSTSEC scanner (govulncheck equivalent).
install_crate cargo-audit cargo-audit

if [ "$MODE" = "--minimal" ]; then
  info "Minimal mode: skipping cargo-deny / cargo-geiger / cargo-nextest / cargo-llvm-cov."
else
  install_crate cargo-deny     cargo-deny
  install_crate cargo-geiger   cargo-geiger
  install_crate cargo-nextest  cargo-nextest
  install_crate cargo-llvm-cov cargo-llvm-cov
  # llvm-tools-preview is required by cargo-llvm-cov to find llvm-cov/llvm-profdata.
  rustup component add llvm-tools-preview >/dev/null 2>&1 || true
fi

# --- 4. final report ------------------------------------------------------
report
ok "Done. Run '/rust-recette <path>' to validate Rust code, or this script with --check to re-verify."
