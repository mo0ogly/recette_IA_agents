#!/usr/bin/env bash
# c37 A40: engine PRE/POST delta verification for pkg/fingerprint/ changes.
#
# Captures verdict counts before AND after the working-tree changes, prints
# a delta report, exits non-zero if any CORRECT regression detected.
#
# Usage:
#   bash verify_engine_delta.sh [--dataset PATH] [--src lia|all] [--threshold N]
#
# Defaults:
#   --dataset = /opt/lia-sec/dev/_alire/temp/onyphe_recette_16641.jsonl
#   --src     = lia
#   --threshold = 0 (any CORRECT regression fails)
#
# Workflow:
#   1. git stash push --include-untracked (preserve current pkg/fingerprint/* edits)
#   2. make recette (rebuild both binaries from clean state)
#   3. recette-onyphe -> PRE verdict counts
#   4. git stash pop (restore working tree)
#   5. make recette (rebuild with changes)
#   6. recette-onyphe -> POST verdict counts
#   7. compute delta CORRECT / MISS / WRONG
#   8. exit 1 if CORRECT delta < -threshold
#
# Incident c36 A34: filter caused -2933 CORRECT regression. This script
# would have surfaced the regression before the commit.

set -euo pipefail

LIAPROBE_DIR="/opt/lia-sec/liaprobe"
DATASET="/opt/lia-sec/dev/_alire/temp/onyphe_recette_16641.jsonl"
SRC="lia"
THRESHOLD=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dataset) DATASET="$2"; shift 2 ;;
        --src) SRC="$2"; shift 2 ;;
        --threshold) THRESHOLD="$2"; shift 2 ;;
        -h|--help)
            sed -n '2,30p' "$0"; exit 0 ;;
        *) echo "Unknown arg: $1" >&2; exit 2 ;;
    esac
done

if [ ! -f "$DATASET" ]; then
    echo "FATAL: dataset not found: $DATASET" >&2
    exit 2
fi
if [ ! -d "$LIAPROBE_DIR" ]; then
    echo "FATAL: liaprobe dir not found: $LIAPROBE_DIR" >&2
    exit 2
fi

# Helper: run recette + emit "CORRECT MISS WRONG" counts as 3 ints space-separated
run_recette() {
    local outfile
    outfile=$(mktemp)
    "$LIAPROBE_DIR/bin/recette-onyphe" -f "$DATASET" -src "$SRC" -out json 2>/dev/null > "$outfile"
    python3 -c "
import sys, json
d = json.load(open('$outfile'))
v = d.get('verdicts') if isinstance(d, dict) else d
if v is None and isinstance(d, dict): v = d.get('results', [])
from collections import Counter
c = Counter(x.get('Verdict') for x in v)
print(c.get('CORRECT', 0), c.get('MISS', 0), c.get('WRONG', 0))
"
    rm -f "$outfile"
}

cd "$LIAPROBE_DIR"

echo "[verify_engine_delta] dataset=$DATASET src=$SRC threshold=$THRESHOLD"
echo "[verify_engine_delta] step 1: stash current changes (push --include-untracked)"
HAS_CHANGES=$(git status --short | wc -l)
STASHED=0
if [ "$HAS_CHANGES" -gt 0 ]; then
    git stash push --include-untracked -m "verify_engine_delta_baseline_$(date -u +%Y%m%d_%H%M%S)" > /dev/null 2>&1
    STASHED=1
fi

echo "[verify_engine_delta] step 2: make recette (baseline)"
make recette > /dev/null 2>&1

echo "[verify_engine_delta] step 3: PRE verdict counts"
PRE=$(run_recette)
PRE_C=$(echo "$PRE" | awk '{print $1}')
PRE_M=$(echo "$PRE" | awk '{print $2}')
PRE_W=$(echo "$PRE" | awk '{print $3}')
echo "[verify_engine_delta] PRE  CORRECT=$PRE_C MISS=$PRE_M WRONG=$PRE_W"

echo "[verify_engine_delta] step 4: restore working tree (stash pop)"
if [ "$STASHED" -eq 1 ]; then
    git stash pop > /dev/null 2>&1
fi

echo "[verify_engine_delta] step 5: make recette (with changes)"
make recette > /dev/null 2>&1

echo "[verify_engine_delta] step 6: POST verdict counts"
POST=$(run_recette)
POST_C=$(echo "$POST" | awk '{print $1}')
POST_M=$(echo "$POST" | awk '{print $2}')
POST_W=$(echo "$POST" | awk '{print $3}')
echo "[verify_engine_delta] POST CORRECT=$POST_C MISS=$POST_M WRONG=$POST_W"

DELTA_C=$((POST_C - PRE_C))
DELTA_M=$((POST_M - PRE_M))
DELTA_W=$((POST_W - PRE_W))

echo ""
echo "[verify_engine_delta] DELTA CORRECT=${DELTA_C:+(+)}$DELTA_C MISS=${DELTA_M:+(+)}$DELTA_M WRONG=${DELTA_W:+(+)}$DELTA_W"

if [ "$DELTA_C" -lt "-$THRESHOLD" ]; then
    echo "[verify_engine_delta] FAIL: CORRECT regression $DELTA_C exceeds threshold -$THRESHOLD"
    exit 1
fi

echo "[verify_engine_delta] PASS: no CORRECT regression above threshold"
exit 0
