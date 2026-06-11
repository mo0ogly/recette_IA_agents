#!/usr/bin/env bash
# safe_commit.sh -- race-safe path-scoped commit for a shared working
# tree that is concurrently mutated by other agents/sessions.
#
# Incident chain that mandated this (all 2026-05-15/16):
#   A128 go.mod stash race ; A134 SP08 staging ; rbac_middleware leak ;
#   dev 9f30bd0567 swept 10 backend-go-global files under an A132 msg ;
#   liaprobe 4761e1e72 foreign SWEETALERT ; A132 6b18f39ae shipped
#   test-only (matcher.go reverted in the git-add window).
#
# Root cause: a plain `git add A B C && git commit` on a tree where a
# parallel track has files pre-staged in the index -> the commit sweeps
# the foreign index. A bad multi-pathspec also aborts `git add` while
# the unconditional commit still fires on the contaminated index.
#
# Protocol enforced here (the one applied by hand 6x, now executable):
#   1. stage ONLY the explicit expected files
#   2. unstage anything else (non-destructive: worktrees preserved)
#   3. verify staged set == exactly the expected set (count + names)
#   4. commit ONLY on exact match, else ABORT (exit 3) -- never sweep
#
# Usage:
#   safe_commit.sh -C <repo> -m <msg> [-n] -- file1 file2 ...
#     -C <repo>  git repo dir (default: cwd)
#     -m <msg>   commit message (required unless -n)
#     -n         dry-run: stage+verify, print, do NOT commit
#   Exit: 0 ok | 2 usage | 3 mismatch/abort (nothing committed)

set -euo pipefail

REPO="$(pwd)"
MSG=""
DRY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    -C) REPO="$2"; shift 2 ;;
    -m) MSG="$2"; shift 2 ;;
    -n) DRY=1; shift ;;
    --) shift; break ;;
    *) echo "usage: safe_commit.sh -C repo -m msg [-n] -- files..." >&2
       exit 2 ;;
  esac
done
FILES=("$@")
[[ ${#FILES[@]} -eq 0 ]] && { echo "no files given" >&2; exit 2; }
[[ $DRY -eq 0 && -z "$MSG" ]] && { echo "-m required" >&2; exit 2; }

cd "$REPO"

# 1. stage only the expected files (tolerate a bad pathspec per file)
for f in "${FILES[@]}"; do
  git add -- "$f" 2>/dev/null || echo "WARN: cannot stage $f" >&2
done

# 2. unstage anything not expected (non-destructive -- worktree intact)
# --no-renames: a `mv`/rename is otherwise collapsed by --name-only to the
# destination path only, so the deleted source path would silently drop out
# of the staged set and mismatch a caller that (correctly) lists BOTH the
# old and new paths. With --no-renames a rename shows as delete(old)+add(new),
# which is exactly what an explicit two-path expected set encodes.
mapfile -t STAGED < <(git diff --cached --no-renames --name-only)
EXPECTED_SORTED="$(printf '%s\n' "${FILES[@]}" | sort -u)"
for s in "${STAGED[@]}"; do
  if ! grep -qxF "$s" <<<"$EXPECTED_SORTED"; then
    git restore --staged -- "$s"
    echo "unstaged FOREIGN: $s" >&2
  fi
done

# 3. verify staged == expected exactly (--no-renames: see note above)
mapfile -t NOW < <(git diff --cached --no-renames --name-only | sort -u)
NOW_JOINED="$(printf '%s\n' "${NOW[@]}")"
if [[ "$NOW_JOINED" != "$EXPECTED_SORTED" ]]; then
  echo "ABORT: staged set != expected set (nothing committed)" >&2
  echo "--- expected ---" >&2; echo "$EXPECTED_SORTED" >&2
  echo "--- staged ---"   >&2; echo "$NOW_JOINED" >&2
  exit 3
fi
echo "staged exactly ${#NOW[@]} expected file(s), zero foreign"

# 4. commit only on exact match
if [[ $DRY -eq 1 ]]; then
  echo "DRY-RUN: would commit ${#NOW[@]} files"
  exit 0
fi
git commit -q -m "$MSG"
git rev-parse --short HEAD
