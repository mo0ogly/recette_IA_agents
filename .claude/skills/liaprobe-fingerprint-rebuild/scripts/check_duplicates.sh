#!/usr/bin/env bash
# check_duplicates.sh -- pre-flight dedup gate for liaprobe-fingerprint-rebuild
#
# Verifies that proposed products in a batch are NOT already AUTHORED in
# previous batches. Cross-references against MASTER_LIST.md (auto-generated
# from all journal.jsonl files) and SESSIONS_INDEX.md.
#
# Usage:
#   ./check_duplicates.sh <proposals_file>
#
# Input: proposals JSON or simple newline-separated product names
# Output:
#   exit 0 = OK (no duplicates above threshold)
#   exit 1 = REJECT (>= 30% duplicates) or hard block on >= 1 dup if --strict
#
# Example:
#   ./check_duplicates.sh sessions/2026-05-08_batch_067/proposals_batch_067.json
#   ./check_duplicates.sh --strict products.txt

set -euo pipefail

THRESHOLD_PCT="${DUP_THRESHOLD_PCT:-30}"
STRICT=0
INPUT=""

for arg in "$@"; do
  case "$arg" in
    --strict) STRICT=1 ;;
    --threshold=*) THRESHOLD_PCT="${arg#--threshold=}" ;;
    -*) echo "Unknown flag: $arg" >&2; exit 2 ;;
    *) INPUT="$arg" ;;
  esac
done

if [ -z "$INPUT" ] || [ ! -f "$INPUT" ]; then
  echo "Usage: $0 [--strict] [--threshold=N] <proposals_file>" >&2
  echo "  Input may be a JSON {rules: [{product: X}, ...]} or newline list" >&2
  exit 2
fi

ROOT="${LIA_TRACKING_ROOT:-/opt/lia-sec/dev/_alire/tracking/liaprobe-fingerprint-rebuild}"
MASTER="${ROOT}/MASTER_LIST.md"
INDEX="${ROOT}/SESSIONS_INDEX.md"

if [ ! -f "$MASTER" ]; then
  echo "ERROR: MASTER_LIST.md missing at $MASTER" >&2
  echo "  Run: ${ROOT}/scripts/build_master_list.sh first" >&2
  exit 2
fi

# Extract product names from input file
extract_products() {
  local f="$1"
  if head -c 1 "$f" | grep -q '{'; then
    jq -r '.rules[]?.product // empty' "$f" 2>/dev/null
  else
    grep -vE '^\s*(#|$)' "$f" | tr '[:lower:]' '[:upper:]' | tr -d ' '
  fi
}

PRODUCTS=$(extract_products "$INPUT")
if [ -z "$PRODUCTS" ]; then
  echo "ERROR: No product names extracted from $INPUT" >&2
  exit 2
fi

TOTAL=0
DUPS=0
DUPS_LIST=()
NEW_LIST=()

while IFS= read -r p; do
  [ -z "$p" ] && continue
  TOTAL=$((TOTAL + 1))
  P_UPPER=$(echo "$p" | tr '[:lower:]' '[:upper:]')

  if grep -qiE "^\| ${P_UPPER} " "$MASTER" 2>/dev/null; then
    EXISTING=$(grep -iE "^\| ${P_UPPER} " "$MASTER" | head -1 | awk -F'|' '{print $3}' | tr -d ' ')
    DUPS=$((DUPS + 1))
    DUPS_LIST+=("${P_UPPER} -> already AUTHORED in ${EXISTING}")
  else
    NEW_LIST+=("${P_UPPER}")
  fi
done <<< "$PRODUCTS"

PCT=0
if [ $TOTAL -gt 0 ]; then
  PCT=$(( DUPS * 100 / TOTAL ))
fi

echo "Pre-flight dedup gate report"
echo "  proposals_file : $INPUT"
echo "  master_list    : $MASTER"
echo "  total products : $TOTAL"
echo "  duplicates     : $DUPS ($PCT%)"
echo "  new uniques    : $((TOTAL - DUPS))"
echo "  threshold      : ${THRESHOLD_PCT}% (strict=$STRICT)"

if [ ${#DUPS_LIST[@]} -gt 0 ]; then
  echo ""
  echo "DUPLICATES DETECTED:"
  printf '  %s\n' "${DUPS_LIST[@]}"
fi

if [ ${#NEW_LIST[@]} -gt 0 ]; then
  echo ""
  echo "NEW UNIQUES:"
  printf '  %s\n' "${NEW_LIST[@]}"
fi

echo ""
if [ $STRICT -eq 1 ] && [ $DUPS -gt 0 ]; then
  echo "VERDICT: REJECT (strict mode, $DUPS duplicate(s) found)"
  exit 1
fi

if [ $PCT -ge $THRESHOLD_PCT ]; then
  echo "VERDICT: REJECT (${PCT}% >= ${THRESHOLD_PCT}%)"
  echo "  Action: revise proposals to keep only NEW UNIQUES, OR mark dups as SKIPPED in SESSION.md"
  exit 1
fi

echo "VERDICT: OK ($PCT% < ${THRESHOLD_PCT}%)"
exit 0
