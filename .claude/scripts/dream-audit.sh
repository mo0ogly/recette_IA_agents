#!/usr/bin/env bash
# dream-audit.sh — Mechanical memory audit for Claude Code
# Usage: bash .claude/scripts/dream-audit.sh [memory_dir]
# Exit codes: 0=CLEAN, 1=NEEDS_CONSOLIDATION, 2=CRITICAL

set -euo pipefail

# Resolve memory directory
if [ -n "${1:-}" ]; then
  MEMORY_DIR="$1"
else
  # Auto-detect: ~/.claude/projects/<project-slug>/memory/
  REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
  SLUG=$(echo "$REPO_ROOT" | sed 's|[/\\:]|-|g; s|^-*||')
  MEMORY_DIR="$HOME/.claude/projects/$SLUG/memory"
fi

INDEX="$MEMORY_DIR/MEMORY.md"
SCORE=0
WARNINGS=0
ERRORS=0

echo "=== DREAM AUDIT ==="
echo "Memory dir: $MEMORY_DIR"
echo "Date: $(date -Iseconds 2>/dev/null || date)"
echo ""

# --- Check 1: Memory directory exists ---
if [ ! -d "$MEMORY_DIR" ]; then
  echo "[SKIP] Memory directory does not exist. Nothing to audit."
  exit 0
fi

# --- Check 2: MEMORY.md exists ---
if [ ! -f "$INDEX" ]; then
  echo "[ERROR] MEMORY.md index missing"
  ERRORS=$((ERRORS + 1))
fi

# --- Check 3: Index sync — files not in index ---
echo "--- Index Sync ---"
for f in "$MEMORY_DIR"/*.md; do
  [ -f "$f" ] || continue
  fname=$(basename "$f")
  [ "$fname" = "MEMORY.md" ] && continue
  if ! grep -q "$fname" "$INDEX" 2>/dev/null; then
    echo "[WARN] Orphan file not in index: $fname"
    WARNINGS=$((WARNINGS + 1))
  fi
done

# --- Check 4: Index sync — index entries without files ---
if [ -f "$INDEX" ]; then
  grep -oE '\([a-zA-Z0-9_-]+\.md\)' "$INDEX" | tr -d '()' | while read -r ref; do
    if [ ! -f "$MEMORY_DIR/$ref" ]; then
      echo "[ERROR] Index references missing file: $ref"
      # Can't increment ERRORS in subshell, use temp file
      echo "1" >> "$MEMORY_DIR/.dream_errors_tmp"
    fi
  done
  if [ -f "$MEMORY_DIR/.dream_errors_tmp" ]; then
    ERRORS=$((ERRORS + $(wc -l < "$MEMORY_DIR/.dream_errors_tmp")))
    rm -f "$MEMORY_DIR/.dream_errors_tmp"
  fi
fi

# --- Check 5: Index line count ---
if [ -f "$INDEX" ]; then
  LINE_COUNT=$(wc -l < "$INDEX")
  echo "--- Index Size ---"
  echo "MEMORY.md: $LINE_COUNT lines"
  if [ "$LINE_COUNT" -gt 200 ]; then
    echo "[ERROR] Index exceeds 200 lines (truncation threshold)"
    ERRORS=$((ERRORS + 1))
  elif [ "$LINE_COUNT" -gt 150 ]; then
    echo "[WARN] Index approaching limit (>150 lines)"
    WARNINGS=$((WARNINGS + 1))
  else
    echo "[OK] Under limit"
  fi
fi

# --- Check 6: Stale files (>30 days since last modified) ---
echo ""
echo "--- Staleness ---"
NOW=$(date +%s)
for f in "$MEMORY_DIR"/*.md; do
  [ -f "$f" ] || continue
  fname=$(basename "$f")
  [ "$fname" = "MEMORY.md" ] && continue
  # Cross-platform: stat -c on Linux, stat -f on macOS, fallback for Git Bash
  MTIME=$(stat -c %Y "$f" 2>/dev/null || stat -f %m "$f" 2>/dev/null || echo "$NOW")
  AGE_DAYS=$(( (NOW - MTIME) / 86400 ))
  if [ "$AGE_DAYS" -gt 30 ]; then
    echo "[WARN] Stale ($AGE_DAYS days): $fname"
    WARNINGS=$((WARNINGS + 1))
  elif [ "$AGE_DAYS" -gt 14 ]; then
    echo "[INFO] Aging ($AGE_DAYS days): $fname"
  fi
done

# --- Check 7: Credential patterns ---
echo ""
echo "--- Credential Scan ---"
CRED_HITS=0
for f in "$MEMORY_DIR"/*.md; do
  [ -f "$f" ] || continue
  if grep -qiE '(password|passwd|secret|token|api.?key)\s*[:=]' "$f" 2>/dev/null; then
    echo "[CRITICAL] Potential credential in: $(basename "$f")"
    CRED_HITS=$((CRED_HITS + 1))
    ERRORS=$((ERRORS + 1))
  fi
done
if [ "$CRED_HITS" -eq 0 ]; then
  echo "[OK] No credentials detected"
fi

# --- Check 8: Duplicate descriptions ---
echo ""
echo "--- Duplicate Detection ---"
DESCRIPTIONS=""
for f in "$MEMORY_DIR"/*.md; do
  [ -f "$f" ] || continue
  fname=$(basename "$f")
  [ "$fname" = "MEMORY.md" ] && continue
  DESC=$(grep -m1 '^description:' "$f" 2>/dev/null | sed 's/^description:\s*//' || echo "")
  if [ -n "$DESC" ]; then
    if echo "$DESCRIPTIONS" | grep -qF "$DESC" 2>/dev/null; then
      echo "[WARN] Duplicate description in $fname: $DESC"
      WARNINGS=$((WARNINGS + 1))
    fi
    DESCRIPTIONS="$DESCRIPTIONS|$DESC"
  fi
done
if [ "$WARNINGS" -eq 0 ] && [ "$ERRORS" -eq 0 ]; then
  echo "[OK] No duplicates"
fi

# --- Check 9: File count ---
echo ""
echo "--- Summary ---"
FILE_COUNT=$(find "$MEMORY_DIR" -maxdepth 1 -name '*.md' ! -name 'MEMORY.md' | wc -l)
TOTAL_LINES=0
for f in "$MEMORY_DIR"/*.md; do
  [ -f "$f" ] || continue
  TOTAL_LINES=$((TOTAL_LINES + $(wc -l < "$f")))
done
echo "Files: $FILE_COUNT (excl. index)"
echo "Total lines: $TOTAL_LINES"
echo "Warnings: $WARNINGS"
echo "Errors: $ERRORS"

# --- Verdict ---
echo ""
if [ "$ERRORS" -gt 0 ]; then
  echo "VERDICT: CRITICAL ($ERRORS errors, $WARNINGS warnings)"
  exit 2
elif [ "$WARNINGS" -gt 2 ]; then
  echo "VERDICT: NEEDS_CONSOLIDATION ($WARNINGS warnings)"
  exit 1
else
  echo "VERDICT: CLEAN"
  exit 0
fi
