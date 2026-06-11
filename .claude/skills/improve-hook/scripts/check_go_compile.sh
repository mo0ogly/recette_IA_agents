#!/bin/bash
# check_go_compile.sh -- backend Go compile gate for the LIA-SEC pre-commit hook.
#
# WHY: 5 commits (5b8d3eaa99..381ef9cdf4) reached master calling undefined
# functions because neither safe_commit.sh nor the pre-commit hook ran go build
# on staged backend Go. `go build ./...` / `go vet ./...` cannot be used in
# cmd/sigma_web (multi-main + standalone tools) -- that is exactly why
# build_secure_lia.sh keeps an explicit whitelist. This gate reuses that SAME
# whitelist and compiles to /dev/null (typecheck only -- no 69M binary, no
# backup, no build lock), so it is faithful to the real build but side-effect
# free.
#
# Delta-scoped: a no-op (exit 0) unless a cmd/sigma_web/*.go file is staged.
#
# Exit codes:
#   0  OK (compiles, or no backend Go staged)
#   1  compile error (commit must be blocked)
#   2  usage / environment error (go missing, build script missing)
#
# Usage:
#   check_go_compile.sh            # uses git staged set (pre-commit mode)
#   check_go_compile.sh --all      # compile the whole whitelist regardless of staging
set -u

# Resolve repo base = three levels up from this script
# (.../dev/.claude/skills/improve-hook/scripts/x.sh -> .../dev)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
BUILD_SCRIPT="$BASE_DIR/cmd/sigma_web/build_secure_lia.sh"

MODE="${1:-staged}"

if ! command -v go >/dev/null 2>&1; then
    echo "check_go_compile: go not found in PATH" >&2
    exit 2
fi
if [ ! -f "$BUILD_SCRIPT" ]; then
    echo "check_go_compile: build_secure_lia.sh not found at $BUILD_SCRIPT" >&2
    exit 2
fi

cd "$BASE_DIR" || exit 2

# Delta-scope: skip entirely unless a backend Go file is staged.
if [ "$MODE" != "--all" ]; then
    STAGED=$(git diff --cached --name-only --diff-filter=ACM 2>/dev/null \
        | grep -E '^cmd/sigma_web/.*\.go$' || true)
    if [ -z "$STAGED" ]; then
        exit 0
    fi
fi

# Compile the UNION of (a) the build_secure_lia.sh whitelist -- the single source
# of truth for what the real binary links -- and (b) the staged backend .go files
# (so a brand-new broken file, not yet in the whitelist, is ALSO caught, not just
# an edit to an already-whitelisted file). Standalone tools (//go:build ignore or
# // +build ignore) are excluded: they are deliberately out of the whitelist and
# carry their own package main / main(), which would break a single-package build.
WHITELIST=$(grep -oE 'cmd/sigma_web/[a-zA-Z0-9_/]+\.go' "$BUILD_SCRIPT" | sort -u)
if [ -z "$WHITELIST" ]; then
    echo "check_go_compile: empty whitelist extracted from build_secure_lia.sh" >&2
    exit 2
fi

STAGED_GO=$(git diff --cached --name-only --diff-filter=ACM 2>/dev/null \
    | grep -E '^cmd/sigma_web/.*\.go$' | grep -vE '_test\.go$' || true)

# Build the compile set: whitelist + staged (deduped), minus build-ignored files.
COMPILE_SET=$(
    {
        printf '%s\n' "$WHITELIST"
        printf '%s\n' "$STAGED_GO"
    } | sort -u | while read -r f; do
        [ -z "$f" ] && continue
        [ -f "$f" ] || continue
        if head -5 "$f" 2>/dev/null | grep -qE '^//(go:build| \+build) ignore'; then
            continue
        fi
        printf '%s\n' "$f"
    done
)
if [ -z "$COMPILE_SET" ]; then
    exit 0
fi

# Typecheck only: -o /dev/null produces no binary, no backup, no lock.
# shellcheck disable=SC2086
if ! BUILD_ERR=$(go build -mod=mod -o /dev/null $COMPILE_SET 2>&1); then
    echo "check_go_compile: backend Go does NOT compile:" >&2
    echo "$BUILD_ERR" | head -20 >&2
    exit 1
fi

# Test-compile gate: a staged *_test.go is invisible to `go build` (skipped by
# design), yet a broken test file still breaks `go test` for the whole package.
# When a backend test file is staged, compile the package's test binary WITHOUT
# running any test (`-run '^$' -count=1`): this typechecks every _test.go in the
# directory. Closes the gap that let a malformed zz_live_gate_test.go slip
# (incident 2026-05-31). Only runs when a _test.go is staged (or --all).
STAGED_TEST=$(git diff --cached --name-only --diff-filter=ACM 2>/dev/null \
    | grep -E '^cmd/sigma_web/.*_test\.go$' || true)
if [ "$MODE" = "--all" ] || [ -n "$STAGED_TEST" ]; then
    # cmd/sigma_web is a Go SUB-MODULE (own go.mod = sigma_web_backend). go test
    # must run from INSIDE it ('.'), not as ./cmd/sigma_web/ from BASE_DIR (which
    # the parent module cannot resolve -> "does not contain package" / setup
    # failed = a false block). cwd via a subshell so BASE_DIR is preserved.
    if ! TEST_ERR=$(cd "$BASE_DIR/cmd/sigma_web" && go test -tags unit -run '^$' -count=1 . 2>&1); then
        echo "check_go_compile: backend Go TEST files do NOT compile:" >&2
        echo "$TEST_ERR" | head -20 >&2
        exit 1
    fi
fi
exit 0
