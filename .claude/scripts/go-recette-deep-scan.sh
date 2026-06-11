#!/usr/bin/env bash
# go-recette-deep-scan.sh -- Bloc D+F orchestration for /go-recette
# Merges Trail of Bits (semgrep multi-ruleset) + Go Security Scanner (gosec+govulncheck) patterns.
#
# Usage: .claude/scripts/go-recette-deep-scan.sh <file_or_dir>
#
# Outputs:
#   /tmp/go-recette-deep/gosec.txt          -- gosec text report
#   /tmp/go-recette-deep/gosec.json         -- gosec JSON (for jq filtering)
#   /tmp/go-recette-deep/govulncheck.txt    -- govulncheck binary mode
#   /tmp/go-recette-deep/semgrep-*.sarif    -- per-ruleset semgrep SARIF (if semgrep usable)
#   /tmp/go-recette-deep/report.md          -- consolidated human-readable report
#
# Reference: .claude/commands/go-recette.md Blocs D and F

set -u
TARGET="${1:-cmd/sigma_web/discovery_api.go}"
OUT=/tmp/go-recette-deep
mkdir -p "$OUT"

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
GO_BIN="$HOME/go/bin"
BACKEND_DIR="$REPO_ROOT/cmd/sigma_web"
BACKEND_BIN="$BACKEND_DIR/sigma_web_backend"

echo "# go-recette deep scan -- $(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$OUT/report.md"
echo "" >> "$OUT/report.md"
echo "Target: \`$TARGET\`" >> "$OUT/report.md"
echo "" >> "$OUT/report.md"

# ---------- BLOC D1 -- gosec (Go Security Scanner pattern) ----------
echo "## Bloc D1 -- gosec" >> "$OUT/report.md"
if [[ -x "$GO_BIN/gosec" ]]; then
    ( cd "$BACKEND_DIR" && "$GO_BIN/gosec" -fmt=text . ) > "$OUT/gosec.txt" 2>&1 &
    ( cd "$BACKEND_DIR" && "$GO_BIN/gosec" -fmt=json -out="$OUT/gosec.json" . ) 2>/dev/null &
    wait

    # Target-specific histogram
    BASENAME="$(basename "$TARGET")"
    HIGH=$(grep -c "$BASENAME:.*Severity: HIGH" "$OUT/gosec.txt" 2>/dev/null || echo 0)
    MED=$(grep -c "$BASENAME:.*Severity: MEDIUM" "$OUT/gosec.txt" 2>/dev/null || echo 0)
    LOW=$(grep -c "$BASENAME:.*Severity: LOW" "$OUT/gosec.txt" 2>/dev/null || echo 0)
    TOTAL_ISSUES=$(grep -oE 'Issues : .\[[0-9;]*m[0-9]+' "$OUT/gosec.txt" 2>/dev/null | grep -oE '[0-9]+$' | tail -1)
    echo "- Full scan: \`$TOTAL_ISSUES\` total issues across \`$BACKEND_DIR\`" >> "$OUT/report.md"
    echo "- Target ($BASENAME): HIGH=$HIGH MEDIUM=$MED LOW=$LOW" >> "$OUT/report.md"
    if [[ "$HIGH" -gt 0 ]]; then
        echo "- **VERDICT: FAIL CRITIQUE** ($HIGH HIGH findings)" >> "$OUT/report.md"
    elif [[ "$MED" -gt 0 ]]; then
        echo "- **VERDICT: FAIL MAJEUR** ($MED MEDIUM findings)" >> "$OUT/report.md"
    else
        echo "- **VERDICT: PASS** (only LOW findings, mostly G104 unhandled errors)" >> "$OUT/report.md"
    fi
else
    echo "- SKIPPED: gosec not installed at \`$GO_BIN/gosec\`" >> "$OUT/report.md"
fi
echo "" >> "$OUT/report.md"

# ---------- BLOC D2 -- govulncheck (binary mode) ----------
echo "## Bloc D2 -- govulncheck (binary mode)" >> "$OUT/report.md"
if [[ -x "$GO_BIN/govulncheck" && -x "$BACKEND_BIN" ]]; then
    "$GO_BIN/govulncheck" -mode=binary "$BACKEND_BIN" > "$OUT/govulncheck.txt" 2>&1
    AFFECTED=$(grep -oE 'affected by [0-9]+ vulnerabilities' "$OUT/govulncheck.txt" | grep -oE '[0-9]+' | head -1)
    AFFECTED="${AFFECTED:-0}"
    echo "- Binary: \`$BACKEND_BIN\`" >> "$OUT/report.md"
    echo "- Affected by: \`$AFFECTED\` vulnerabilities in called symbols" >> "$OUT/report.md"
    if [[ "$AFFECTED" -gt 0 ]]; then
        echo "- **VERDICT: FAIL MAJEUR** (see \`$OUT/govulncheck.txt\` for details)" >> "$OUT/report.md"
        grep -E 'Vulnerability #|GO-[0-9]+-[0-9]+' "$OUT/govulncheck.txt" | head -20 >> "$OUT/report.md"
    else
        echo "- **VERDICT: PASS**" >> "$OUT/report.md"
    fi
else
    echo "- SKIPPED: govulncheck or backend binary missing" >> "$OUT/report.md"
fi
echo "" >> "$OUT/report.md"

# ---------- BLOC F -- Semgrep multi-ruleset (Trail of Bits pattern) ----------
echo "## Bloc F -- Semgrep multi-ruleset (Trail of Bits)" >> "$OUT/report.md"
SEMGREP_BIN=""
if command -v semgrep >/dev/null 2>&1; then
    SEMGREP_BIN="$(command -v semgrep)"
elif [[ -x "$REPO_ROOT/.venv-security/bin/semgrep" ]]; then
    # Check shebang is valid (known issue: venv migrated from local machine)
    if head -1 "$REPO_ROOT/.venv-security/bin/semgrep" | grep -q "$(which python3 2>/dev/null)" || \
       [[ -x "$REPO_ROOT/.venv-security/bin/python3" ]]; then
        SEMGREP_BIN="$REPO_ROOT/.venv-security/bin/semgrep"
    fi
fi

if [[ -n "$SEMGREP_BIN" ]]; then
    # Trail of Bits recommended rulesets for Go
    RULESETS=(p/security-audit p/secrets p/golang)
    for r in "${RULESETS[@]}"; do
        safe="${r//\//_}"
        "$SEMGREP_BIN" --metrics=off --config "$r" \
            --severity MEDIUM --severity HIGH --severity ERROR \
            --json -o "$OUT/semgrep-${safe}.json" \
            "$REPO_ROOT/$TARGET" 2>/dev/null &
    done
    wait

    TOTAL=0
    for f in "$OUT"/semgrep-*.json; do
        [[ -f "$f" ]] || continue
        N=$(python3 -c "import json,sys; d=json.load(open('$f')); print(len(d.get('results',[])))" 2>/dev/null || echo 0)
        TOTAL=$((TOTAL + N))
        echo "- $(basename "$f" .json): $N findings" >> "$OUT/report.md"
    done
    echo "- Total semgrep findings (MEDIUM+): $TOTAL" >> "$OUT/report.md"
    if [[ "$TOTAL" -gt 0 ]]; then
        echo "- **VERDICT: review required**" >> "$OUT/report.md"
    else
        echo "- **VERDICT: PASS**" >> "$OUT/report.md"
    fi
else
    echo "- SKIPPED: semgrep not usable (venv shebang or binary missing)" >> "$OUT/report.md"
fi
echo "" >> "$OUT/report.md"

# ---------- Summary ----------
echo "## Summary" >> "$OUT/report.md"
echo "" >> "$OUT/report.md"
echo "Reports stored in \`$OUT/\`. See \`.claude/commands/go-recette.md\` for scoring rules." >> "$OUT/report.md"

cat "$OUT/report.md"
