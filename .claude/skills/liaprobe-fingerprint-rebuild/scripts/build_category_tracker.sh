#!/usr/bin/env bash
# build_category_tracker.sh -- regenerate CATEGORY_TRACKER.md
#
# Reads each AUTHORED rule's `category` field from the .json file and
# tabulates by category: count, last batch, sample products.
#
# Usage:
#   ./build_category_tracker.sh

set -euo pipefail

ROOT="${LIA_TRACKING_ROOT:-/opt/lia-sec/dev/_alire/tracking/liaprobe-fingerprint-rebuild}"
PATTERNS="${LIAPROBE_PATTERNS:-/opt/lia-sec/liaprobe/patterns/web-signatures}"
TRACKER="${ROOT}/CATEGORY_TRACKER.md"
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)

if [ ! -d "$PATTERNS" ]; then
  echo "ERROR: patterns dir missing: $PATTERNS" >&2
  exit 2
fi

TMP_CATS=$(mktemp)
trap 'rm -f "$TMP_CATS"' EXIT

# Extract category from each .json (fast: jq processes all files)
find "$PATTERNS" -maxdepth 1 -name "*.json" -type f -print0 \
  | xargs -0 -n 50 jq -rc 'input_filename as $f
      | [(.category // "uncategorized"),
         ($f | split("/") | last | rtrimstr(".json"))]
      | @tsv' 2>/dev/null \
  | awk -F'\t' '{print $1"|"$2}' \
  > "$TMP_CATS"

# Aggregate per category
{
  echo "# Category Tracker -- Theme rotation guide (auto-generated)"
  echo ""
  echo "**Generated** : $TS"
  echo "**Source**    : .category field across $PATTERNS/*.json"
  echo ""
  echo "Use this file BEFORE picking a batch theme. Pick a category that is"
  echo "either underrepresented or hasn't been touched recently (rotation)."
  echo ""
  echo "DO NOT EDIT MANUALLY. Regenerate via:"
  echo ""
  echo '```bash'
  echo "${ROOT}/scripts/build_category_tracker.sh"
  echo '```'
  echo ""
  echo "## Categories"
  echo ""
  echo "| Category | Count | Sample products (5 first) |"
  echo "|----------|-------|---------------------------|"

  awk -F'|' '
    {
      cat = $1
      count[cat]++
      if (samples[cat] == "") {
        samples[cat] = $2
      } else if (split(samples[cat], a, ", ") < 5) {
        samples[cat] = samples[cat] ", " $2
      }
    }
    END {
      for (c in count) {
        print count[c] "|" c "|" samples[c]
      }
    }
  ' "$TMP_CATS" \
  | sort -t'|' -k1,1 -nr \
  | awk -F'|' '{printf "| %s | %d | %s |\n", $2, $1, $3}'

  echo ""
  echo "## Theme rotation rule"
  echo ""
  echo "BEFORE starting a new batch:"
  echo "1. Check this file. Identify the 3 categories with HIGHEST count -- avoid them"
  echo "2. Pick a category from the bottom half (under 50 products)"
  echo "3. Pick a category that was NOT touched in the last 5 batches (check SESSIONS_INDEX.md)"
  echo "4. If proposing >= 3 products from same crowded category -> reject batch"
} > "$TRACKER"

echo "OK Generated:"
echo "  $TRACKER"
