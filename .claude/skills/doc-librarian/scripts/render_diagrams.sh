#!/usr/bin/env bash
# render_diagrams.sh -- Pre-render Category A Mermaid diagrams to SVG using mmdc
# Category A = stable diagrams rendered at build time (26 diagrams)
# Category B = evolving diagrams rendered at runtime by mermaid.js (4 diagrams)
# Usage: bash render_diagrams.sh [--force] [--diagram <name>]

set -euo pipefail

DIAGRAMS_DIR="${DIAGRAMS_DIR:-_alire/01_DOCUMENTATION/diagrams}"
SVG_OUT="${SVG_OUT:-_alire/01_DOCUMENTATION/diagrams/svg}"
FORCE="${1:-}"

# Category B diagrams (runtime rendering, skip mmdc pre-render)
CATEGORY_B=(
    "pdca_swarm_sequence"
    "apex_swarm_sequence"
    "ai_fallback_chain"
    "etl_orchestrator"
)

mkdir -p "$SVG_OUT"

# Check mmdc is available
if ! command -v mmdc &>/dev/null; then
    echo "[ERROR] mmdc not found. Install: npm install -g @mermaid-js/mermaid-cli"
    echo "[ERROR] Also required: chromium-browser fonts-jetbrains-mono"
    exit 1
fi

# Find all .mmd files
MMD_FILES=("$DIAGRAMS_DIR"/*.mmd)
if [ ${#MMD_FILES[@]} -eq 0 ]; then
    echo "[WARN] No .mmd files found in $DIAGRAMS_DIR"
    exit 0
fi

RENDERED=0
SKIPPED=0
ERRORS=0

for mmd_file in "${MMD_FILES[@]}"; do
    [ -f "$mmd_file" ] || continue

    stem=$(basename "$mmd_file" .mmd)
    svg_out="$SVG_OUT/${stem}.svg"

    # Skip Category B (runtime rendering)
    skip=false
    for cat_b in "${CATEGORY_B[@]}"; do
        if [ "$stem" = "$cat_b" ]; then
            skip=true
            break
        fi
    done
    if $skip; then
        echo "[SKIP] $stem (Category B -- runtime rendering)"
        ((SKIPPED++)) || true
        continue
    fi

    # Skip if SVG exists and .mmd not modified (unless --force)
    if [ -f "$svg_out" ] && [ "$FORCE" != "--force" ]; then
        if [ "$mmd_file" -ot "$svg_out" ]; then
            echo "[CACHE] $stem (SVG up-to-date)"
            ((SKIPPED++)) || true
            continue
        fi
    fi

    # Validate the %%{init ...}%% directive is present.
    # Match the prefix "%%{init" only -- the real syntax is "%%{init:" (colon),
    # so a literal "%%{init}" search is a false negative on every valid file.
    if ! grep -q '%%{init' "$mmd_file"; then
        echo "[WARN] $stem: missing %%{init ...}%% block -- skipping (fix the .mmd file first)"
        ((ERRORS++)) || true
        continue
    fi

    # Render SVG
    echo "[RENDER] $stem -> $svg_out"
    if mmdc \
        --input "$mmd_file" \
        --output "$svg_out" \
        --theme dark \
        --backgroundColor "#050d1a" \
        --puppeteerConfigFile /dev/null \
        2>/dev/null; then
        ((RENDERED++)) || true
    else
        echo "[ERROR] Failed to render $stem"
        ((ERRORS++)) || true
    fi
done

echo ""
echo "=== Render Summary ==="
echo "Rendered : $RENDERED"
echo "Skipped  : $SKIPPED (cache or Category B)"
echo "Errors   : $ERRORS"

if [ "$ERRORS" -gt 0 ]; then
    echo "[WARN] $ERRORS diagrams failed. Check .mmd syntax and %%{init}%% presence."
    exit 1
fi

echo "[OK] SVG diagrams ready in $SVG_OUT"
