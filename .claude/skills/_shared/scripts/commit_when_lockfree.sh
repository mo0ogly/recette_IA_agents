#!/usr/bin/env bash
# commit_when_lockfree.sh -- opportunistic commit wrapper for shared git trees
#
# Context: in a multi-track environment where multiple agent sessions write to the
# same git working tree concurrently, .git/index.lock is frequently held by a
# parallel track. A plain safe_commit call fails immediately if the lock is
# present. This wrapper retries until the lock is free (or a timeout is reached),
# then delegates to safe_commit.sh for the actual staged-only, exact-match commit,
# and optionally retries the push on the same lock-free condition.
#
# safe_commit.sh (R28): stages ONLY the explicit files, unstages any foreign
# staged files (non-destructive), verifies exact match, then commits. It uses
# set -euo pipefail and exits 3 on any mismatch -- nothing is committed.
#
# Usage:
#   commit_when_lockfree.sh -C <repo> -m "<msg>" [--max-attempts N] [--no-push] -- file1 file2 ...
#
# Options:
#   -C <repo>          path to the git repository (default: current directory)
#   -m <msg>           commit message (required)
#   --max-attempts N   max lock-free poll cycles for commit phase (default: 300)
#   --no-push          skip push after commit
#   --pathspec         commit via `git commit -- <files>` instead of safe_commit.
#                      Index-state-independent: commits ONLY the named paths from
#                      the worktree, so it does NOT sweep a foreign index and is
#                      NOT aborted by a parallel track mutating the index during a
#                      stage->verify window (the exact failure mode that makes the
#                      default safe_commit path return exit 3 under heavy
#                      concurrency). Handles renames/deletions natively. Use this
#                      for rename/delete-heavy commits or when the default path
#                      keeps aborting under concurrent index churn. Trade-off: it
#                      relies on git pathspec scoping rather than safe_commit's
#                      explicit staged-set exact-match assertion.
#
# Exit codes:
#   0  commit (and optional push) succeeded
#   2  usage error or safe_commit.sh not found
#   3  timeout: foreign tracks held git busy; or safe_commit mismatch/abort
#
# Environment overrides:
#   SAFE_COMMIT   path to safe_commit.sh (default: <repo>/.claude/skills/liaprobe-fingerprint-rebuild/scripts/safe_commit.sh)
#   PUSH_ATTEMPTS max lock-free poll cycles for push phase (default: 60)

set -uo pipefail

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
REPO="$(pwd)"
MSG=""
MAX_ATTEMPTS=300
NO_PUSH=0
PATHSPEC=0
PUSH_ATTEMPTS="${PUSH_ATTEMPTS:-60}"

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
if [[ $# -eq 0 ]]; then
  echo "usage: commit_when_lockfree.sh -C <repo> -m <msg> [--max-attempts N] [--no-push] -- file1 file2 ..." >&2
  exit 2
fi

FILES=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    -C) REPO="$2"; shift 2 ;;
    -m) MSG="$2"; shift 2 ;;
    --max-attempts) MAX_ATTEMPTS="$2"; shift 2 ;;
    --no-push) NO_PUSH=1; shift ;;
    --pathspec) PATHSPEC=1; shift ;;
    --) shift; FILES=("$@"); break ;;
    -*)
      echo "unknown option: $1" >&2
      echo "usage: commit_when_lockfree.sh -C <repo> -m <msg> [--max-attempts N] [--no-push] [--pathspec] -- file1 file2 ..." >&2
      exit 2
      ;;
    *)
      echo "unexpected positional argument before '--': $1" >&2
      exit 2
      ;;
  esac
done

if [[ -z "$MSG" ]]; then
  echo "error: -m <msg> is required" >&2
  exit 2
fi

if [[ ${#FILES[@]} -eq 0 ]]; then
  echo "error: no files given after '--'" >&2
  exit 2
fi

# Resolve safe_commit.sh (only needed for the default staged-set path, not --pathspec).
SAFE_COMMIT="${SAFE_COMMIT:-${REPO}/.claude/skills/liaprobe-fingerprint-rebuild/scripts/safe_commit.sh}"
if [[ $PATHSPEC -eq 0 && ! -x "$SAFE_COMMIT" ]]; then
  echo "error: safe_commit.sh not found or not executable: ${SAFE_COMMIT}" >&2
  echo "  set SAFE_COMMIT env var to the correct path, or ensure the script exists." >&2
  echo "  (or pass --pathspec to commit via 'git commit -- files' without safe_commit)" >&2
  exit 2
fi

# ---------------------------------------------------------------------------
# Helper: check whether .git/index.lock exists in the target repo
# ---------------------------------------------------------------------------
lock_is_free() {
  [[ ! -f "${REPO}/.git/index.lock" ]]
}

# ---------------------------------------------------------------------------
# Helper: derive a short slug from the commit message for post-commit
# verification via git log. We search for the first 20 chars of the message
# (printable ASCII only) to avoid regex quoting problems.
# ---------------------------------------------------------------------------
msg_slug() {
  # Take the first 20 characters, strip non-alphanumeric except space/dash
  printf '%s' "$MSG" | head -c 20 | tr -d '\n' | sed 's/[^A-Za-z0-9 _\-]//g'
}

# ---------------------------------------------------------------------------
# Phase 1: wait for lock-free window then call safe_commit
# ---------------------------------------------------------------------------
echo "[commit_when_lockfree] waiting for index.lock to be free (max ${MAX_ATTEMPTS}s)..."

attempt=0
committed=0
while [[ $attempt -lt $MAX_ATTEMPTS ]]; do
  if lock_is_free; then
    if [[ $PATHSPEC -eq 1 ]]; then
      # Index-independent commit: scope strictly to the named paths from the
      # worktree. Does not stage, does not touch a foreign index, survives a
      # parallel track mutating the index, handles renames/deletions natively.
      echo "[commit_when_lockfree] lock free at attempt ${attempt}, committing via pathspec..."
      git_err=""
      # Stage the named paths first: `git commit -- <pathspec>` only commits
      # TRACKED changes, so untracked/new files would be skipped without an add.
      # The add stages new files, renames and deletions for these paths; the
      # subsequent `git commit -- <pathspec>` is still scoped strictly to them,
      # so any foreign-staged file in the shared index is NOT included.
      git -C "${REPO}" add -- "${FILES[@]}" 2>/dev/null || true
      if git -C "${REPO}" commit -q -m "${MSG}" -- "${FILES[@]}" 2>/tmp/cwlf_err; then
        committed=1
        break
      fi
      git_err="$(tail -2 /tmp/cwlf_err 2>/dev/null)"
      case "$git_err" in
        *index.lock*|*"Another git process"*)
          # Lock reappeared between the check and the commit: retry.
          : ;;
        *"nothing to commit"*|*"no changes added"*|*"did not match any file"*)
          echo "[commit_when_lockfree] nothing to commit for these paths (already committed?)" >&2
          git --no-optional-locks -C "${REPO}" log --oneline -1 >&2
          committed=1
          break ;;
        *)
          echo "[commit_when_lockfree] git commit error: ${git_err}" >&2
          # Non-lock error -- retry a few cycles in case it is transient hook contention.
          : ;;
      esac
    else
      echo "[commit_when_lockfree] lock free at attempt ${attempt}, calling safe_commit..."
      # safe_commit exits 0 on success, 3 on mismatch/abort, 2 on usage.
      # We do NOT use 'set -e' here intentionally so we can capture the exit code.
      "${SAFE_COMMIT}" -C "${REPO}" -m "${MSG}" -- "${FILES[@]}"
      sc_exit=$?
      if [[ $sc_exit -eq 0 ]]; then
        committed=1
        break
      elif [[ $sc_exit -eq 3 ]]; then
        # Exact mismatch or index swept by foreign track: treat as fatal, not retryable.
        echo "[commit_when_lockfree] safe_commit aborted (exit 3: mismatch or foreign index sweep)" >&2
        echo "[commit_when_lockfree] hint: retry with --pathspec under heavy concurrent index churn" >&2
        exit 3
      else
        # Exit 2 = usage error in safe_commit -- not retryable.
        echo "[commit_when_lockfree] safe_commit usage error (exit ${sc_exit})" >&2
        exit 2
      fi
    fi
  fi
  sleep 1
  attempt=$((attempt + 1))
done

if [[ $committed -eq 0 ]]; then
  echo "[commit_when_lockfree] TIMEOUT: foreign tracks held git busy for ${MAX_ATTEMPTS}s, commit aborted" >&2
  exit 3
fi

echo "[commit_when_lockfree] commit succeeded"

# ---------------------------------------------------------------------------
# Phase 2 (optional): push when lock-free
# ---------------------------------------------------------------------------
if [[ $NO_PUSH -eq 1 ]]; then
  echo "[commit_when_lockfree] --no-push: skipping push"
  exit 0
fi

echo "[commit_when_lockfree] waiting for index.lock to be free before push (max ${PUSH_ATTEMPTS}s)..."
push_attempt=0
pushed=0
while [[ $push_attempt -lt $PUSH_ATTEMPTS ]]; do
  if lock_is_free; then
    echo "[commit_when_lockfree] pushing..."
    if git --no-optional-locks -C "${REPO}" push; then
      pushed=1
      break
    else
      # Push failure is not a lock issue -- report but do not retry indefinitely.
      echo "[commit_when_lockfree] push failed (non-lock error)" >&2
      break
    fi
  fi
  sleep 1
  push_attempt=$((push_attempt + 1))
done

if [[ $pushed -eq 0 && $NO_PUSH -eq 0 ]]; then
  echo "[commit_when_lockfree] push did not complete (timeout or push error); commit is local" >&2
  # Exit 0: the commit itself succeeded. The caller decides whether push failure is fatal.
fi

exit 0
