#!/usr/bin/env bash
# build_master_list.sh -- regenerate MASTER_LIST.md and MASTER_TODO_LIST.md
#
# Aggregates all journal.jsonl per-batch entries into a deduplicated table
# of AUTHORED products, then cross-references against the live patterns/
# directory to produce a TODO list with checkboxes.
#
# Outputs:
#   MASTER_LIST.md       -- deduplicated AUTHORED products (one row each)
#   MASTER_TODO_LIST.md  -- full inventory: every .json under
#                            patterns/web-signatures/ with [x] AUTHORED in
#                            journals, [.] FILE_ONLY (json exists but no
#                            journal entry = legacy/pre-tracking authoring),
#                            [ ] PENDING (proposed but not yet processed)
#
# Usage:
#   ./build_master_list.sh
#
# Configuration via env:
#   LIA_TRACKING_ROOT   default /opt/lia-sec/dev/_alire/tracking/liaprobe-fingerprint-rebuild
#   LIAPROBE_PATTERNS   default /opt/lia-sec/liaprobe/patterns/web-signatures

set -euo pipefail

ROOT="${LIA_TRACKING_ROOT:-/opt/lia-sec/dev/_alire/tracking/liaprobe-fingerprint-rebuild}"
PATTERNS="${LIAPROBE_PATTERNS:-/opt/lia-sec/liaprobe/patterns/web-signatures}"
SESSIONS="${ROOT}/sessions"
MASTER="${ROOT}/MASTER_LIST.md"
TODO="${ROOT}/MASTER_TODO_LIST.md"

if [ ! -d "$SESSIONS" ]; then
  echo "ERROR: sessions dir missing: $SESSIONS" >&2
  exit 2
fi

if [ ! -d "$PATTERNS" ]; then
  echo "ERROR: patterns dir missing: $PATTERNS" >&2
  exit 2
fi

TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
TMP_AUTHORED=$(mktemp)
TMP_FILES=$(mktemp)
TMP_JOURNAL=$(mktemp)
trap 'rm -f "$TMP_AUTHORED" "$TMP_FILES" "$TMP_JOURNAL"' EXIT

# Step 1: collect all AUTHORED entries from every journal.jsonl
# Format: PRODUCT|BATCH_DIR|DATE|VERDICT
# Single jq invocation per journal (fast)
find "$SESSIONS" -name journal.jsonl -type f -size +0 | while read -r J; do
  BATCH=$(basename "$(dirname "$J")")
  jq -rc --arg b "$BATCH" '
    select(.verdict == "AUTHORED")
    | [.product, $b, ((.timestamp // "") | split("T")[0]), .verdict]
    | @tsv
  ' "$J" 2>/dev/null \
    | awk -F'\t' -v OFS='|' '{print $1, $2, $3, $4}' \
    >> "$TMP_JOURNAL"
done

# Dedup: keep only first authoring per product (lowest batch number)
sort -t'|' -k1,1 -k2,2 "$TMP_JOURNAL" | awk -F'|' '!seen[$1]++' > "$TMP_AUTHORED"

# Step 2: list all .json rules currently in patterns dir (uppercase convention)
find "$PATTERNS" -maxdepth 1 -name "*.json" -type f -printf '%f\n' \
  | sed 's/\.json$//' \
  | grep -E '^[A-Z][A-Z0-9_]*$' \
  | sort -u > "$TMP_FILES"

TOTAL_FILES=$(wc -l < "$TMP_FILES")
TOTAL_AUTHORED=$(wc -l < "$TMP_AUTHORED")

# Step 3: write MASTER_LIST.md (only AUTHORED via journal)
{
  echo "# Master List -- AUTHORED products (auto-generated)"
  echo ""
  echo "**Generated** : $TS"
  echo "**Source**    : aggregation of all sessions/*/journal.jsonl"
  echo "**Total**     : $TOTAL_AUTHORED unique AUTHORED products"
  echo ""
  echo "DO NOT EDIT MANUALLY. Regenerate via:"
  echo ""
  echo '```bash'
  echo "${ROOT}/scripts/build_master_list.sh"
  echo '```'
  echo ""
  echo "| Product | First batch | Date | Verdict |"
  echo "|---------|-------------|------|---------|"
  awk -F'|' '{printf "| %s | %s | %s | %s |\n", $1, $2, $3, $4}' "$TMP_AUTHORED"
} > "$MASTER"

# Step 4: write MASTER_TODO_LIST.md (full inventory + checkboxes)
{
  echo "# Master TODO List -- Full inventory (auto-generated)"
  echo ""
  echo "**Generated** : $TS"
  echo "**Patterns dir** : $PATTERNS"
  echo ""
  echo "Legend :"
  echo "- \`[x]\` AUTHORED  = .json present AND journal.jsonl entry with verdict=AUTHORED"
  echo "- \`[.]\` FILE_ONLY = .json present BUT no journal entry (legacy pre-tracking authoring)"
  echo "- \`[ ]\` PENDING   = proposed in proposals_*.json but not yet processed"
  echo ""
  echo "DO NOT EDIT MANUALLY. Regenerate via:"
  echo ""
  echo '```bash'
  echo "${ROOT}/scripts/build_master_list.sh"
  echo '```'
  echo ""

  echo "## Inventory"
  echo ""
  echo "| Status | Product | Batch | Date |"
  echo "|--------|---------|-------|------|"

  # Fast join: index TMP_AUTHORED in awk, walk TMP_FILES once
  awk -F'|' -v outfile=/tmp/_master_counts.$$ '
    NR==FNR { auth[$1]=$2"|"$3; next }
    {
      if ($1 in auth) {
        split(auth[$1], a, "|")
        printf("| [x] AUTHORED | %s | %s | %s |\n", $1, a[1], a[2])
        c1++
      } else {
        printf("| [.] FILE_ONLY | %s | - | - |\n", $1)
        c2++
      }
    }
    END { print c1+0 > outfile; print c2+0 >> outfile }
  ' "$TMP_AUTHORED" "$TMP_FILES"

  AUTHORED_CNT=$(sed -n 1p /tmp/_master_counts.$$ 2>/dev/null || echo 0)
  FILE_ONLY_CNT=$(sed -n 2p /tmp/_master_counts.$$ 2>/dev/null || echo 0)
  rm -f /tmp/_master_counts.$$

  echo ""
  echo "## Summary"
  echo ""
  echo "| Status | Count |"
  echo "|--------|-------|"
  echo "| [x] AUTHORED (in journal) | $AUTHORED_CNT |"
  echo "| [.] FILE_ONLY (legacy)    | $FILE_ONLY_CNT |"
  echo "| [ ] PENDING               | (see proposals_*.json per active batch) |"
  echo "| Total .json files         | $TOTAL_FILES |"
} > "$TODO"

echo "OK Generated:"
echo "  $MASTER ($TOTAL_AUTHORED AUTHORED via journal)"
echo "  $TODO ($TOTAL_FILES total .json files)"
