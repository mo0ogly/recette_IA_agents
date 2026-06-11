#!/bin/bash
# Synchronise un pattern fingerprint depuis lia/ vers by-taxonomy/ et liaprobe/data/
# Usage: sync_fingerprints.sh <TAXONOMY.json> | sync_fingerprints.sh --all
set -euo pipefail

BASE="/opt/lia-sec/dev"
LIA_DIR="$BASE/data/fingerprints/lia"
TAXO_DIR="$BASE/data/fingerprints/by-taxonomy"
PROBE_DIR="$BASE/liaprobe/data/fingerprints/by-taxonomy"

sync_one() {
    local file="$1"
    local basename=$(basename "$file")

    # Find category in by-taxonomy
    local taxo_match=$(find "$TAXO_DIR" -name "$basename" 2>/dev/null | head -1)
    if [ -n "$taxo_match" ]; then
        cp "$file" "$taxo_match"
        local category=$(basename "$(dirname "$taxo_match")")
        local probe_dest="$PROBE_DIR/$category/$basename"
        if [ -d "$(dirname "$probe_dest")" ]; then
            cp "$file" "$probe_dest"
        fi
        echo "OK: $basename -> by-taxonomy/$category/ + liaprobe/"
    else
        echo "WARN: $basename not found in by-taxonomy/, skipping"
    fi
}

if [ "${1:-}" = "--all" ]; then
    count=0
    for f in "$LIA_DIR"/*.json; do
        [ -f "$f" ] && sync_one "$f" && count=$((count + 1))
    done
    echo "Synced $count patterns"
elif [ -n "${1:-}" ]; then
    if [ -f "$LIA_DIR/$1" ]; then
        sync_one "$LIA_DIR/$1"
    elif [ -f "$1" ]; then
        sync_one "$1"
    else
        echo "ERROR: File not found: $1"
        exit 1
    fi
else
    echo "Usage: $0 <TAXONOMY.json> | $0 --all"
    exit 1
fi
