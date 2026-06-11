#!/usr/bin/env bash
# untracked_source_guard.sh -- SessionStart guard (R31).
#
# Why: 2026-05-24 a single branch had 403,696 untracked files. Genuine source
# (code, LIA-Scan rule YAMLs, surveys, skills, docs, migrations) was DROWNED in
# generated-data noise (json/csv/sarif/logs/binaries), so `git status` was
# useless and real work sat untracked for months -- exactly the loss class that
# the R30 git-restore deletion incident exploited.
#
# This guard counts ONLY genuine untracked SOURCE files (excluding data/logs/
# binaries) and emits a WARNING into session context when the count exceeds a
# threshold, so accumulation can never again grow silently. Non-blocking.
#
# Output on stdout is injected into the session context at SessionStart.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo .)"
cd "$ROOT" 2>/dev/null || exit 0

# Threshold: above this many untracked SOURCE files, warn.
THRESHOLD="${LIA_UNTRACKED_SOURCE_THRESHOLD:-30}"

# List untracked files (gitignore-respecting), then keep only genuine source.
# Excludes generated data (csv/sarif/log/txt), binaries, and disabled/backup junk.
mapfile -t SRC < <(git ls-files --others --exclude-standard 2>/dev/null | grep -E \
  '(\.(go|tsx|ts|jsx|js|py|sql|css|mmd)$|^lia_rules/.*\.yml$|^config/(survey|mappings)/.*\.json$|^_alire/01_DOCUMENTATION/.*\.md$|^\.claude/.*\.(md|sh|cjs|json)$|migrations/.*\.sql$)' \
  | grep -vE '\.(disabled|old|new|bak)$' || true)

COUNT="${#SRC[@]}"

if [ "$COUNT" -gt "$THRESHOLD" ]; then
  echo "UNTRACKED SOURCE GUARD (R31): $COUNT genuine untracked source files (threshold $THRESHOLD)."
  echo "Risk: uncommitted source can be lost (see R30). Commit them this session OR gitignore if generated."
  echo "Top untracked source (first 15):"
  printf '  %s\n' "${SRC[@]:0:15}"
  echo "Full list: git ls-files --others --exclude-standard | grep -E '\\.(go|tsx|ts|py|sql)\$|lia_rules/.*\\.yml\$'"
fi
exit 0
