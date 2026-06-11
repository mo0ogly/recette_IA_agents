#!/usr/bin/env bash
# PPTX visual recette -- converts a PPTX to per-slide PNG via libreoffice headless
# and runs 10 quality checks. Exits 0 on SUCCESS, 1 on PARTIAL, 2 on FAILURE.
#
# Usage: pptx_visual_recette.sh <pptx_file> <expected_slide_count>
#
# Source: PDCA debt closure 2026-04-15

set -euo pipefail

PPTX_FILE="${1:?missing pptx file argument}"
EXPECTED_SLIDES="${2:?missing expected slide count argument}"

if [[ ! -f "$PPTX_FILE" ]]; then
    echo "FAIL: file not found: $PPTX_FILE" >&2
    exit 2
fi

TS="$(date +%Y%m%d_%H%M%S)"
ART_DIR="_alire/temp/pptx_recette/${TS}"
REPORT="${ART_DIR}/report.md"
mkdir -p "$ART_DIR"

PASS=0
FAIL=0
WARN=0

log_check() {
    local status="$1" name="$2" detail="${3:-}"
    echo "| $name | $status | $detail |" >> "$REPORT"
    case "$status" in
        PASS) PASS=$((PASS+1)) ;;
        FAIL) FAIL=$((FAIL+1)) ;;
        WARN) WARN=$((WARN+1)) ;;
    esac
}

{
    echo "# PPTX visual recette report"
    echo
    echo "File: \`$PPTX_FILE\`"
    echo "Expected slides: $EXPECTED_SLIDES"
    echo "Timestamp: $TS"
    echo
    echo "| Check | Status | Detail |"
    echo "|-------|--------|--------|"
} > "$REPORT"

# V1 file size
SIZE=$(stat -c%s "$PPTX_FILE" 2>/dev/null || echo 0)
if [[ "$SIZE" -gt 10240 ]]; then
    log_check PASS "V1 file size" "${SIZE} bytes"
else
    log_check FAIL "V1 file size" "${SIZE} bytes (< 10KB)"
fi

# V2 ZIP parse
# grep -q closes pipe early causing SIGPIPE on unzip under pipefail; materialize output first.
ZIP_LIST=$(unzip -l "$PPTX_FILE" 2>/dev/null || true)
if echo "$ZIP_LIST" | grep -q "ppt/presentation.xml"; then
    log_check PASS "V2 ZIP parse" "presentation.xml present"
else
    log_check FAIL "V2 ZIP parse" "ppt/presentation.xml missing"
    echo "FAIL: PPTX corrupt, aborting" >&2
    exit 2
fi

# V3 LibreOffice conversion
if command -v soffice >/dev/null 2>&1; then
    SOFFICE_LOG="${ART_DIR}/soffice.log"
    if soffice --headless --convert-to pdf --outdir "$ART_DIR" "$PPTX_FILE" > "$SOFFICE_LOG" 2>&1; then
        PDF_FILE="${ART_DIR}/$(basename "${PPTX_FILE%.pptx}.pdf")"
        log_check PASS "V3 soffice convert" "PDF generated"
    else
        log_check FAIL "V3 soffice convert" "exit $? (see $SOFFICE_LOG)"
        echo "FAIL: conversion failed" >&2
        exit 2
    fi
else
    log_check WARN "V3 soffice convert" "soffice not installed, falling back to ZIP static analysis"
    PDF_FILE=""
fi

# V4z ZIP-based slide count. WARN only when mismatch vs expected; the actual
# authoritative count is V4 (pdfinfo) because some PPTX generators leave an
# unreferenced slideN.xml in the zip that presentation.xml ignores.
ZIP_SLIDE_COUNT=$(unzip -l "$PPTX_FILE" 2>/dev/null | grep -cE "ppt/slides/slide[0-9]+\.xml" || true)
if [[ "$ZIP_SLIDE_COUNT" == "$EXPECTED_SLIDES" ]]; then
    log_check PASS "V4z slide count (ZIP)" "$ZIP_SLIDE_COUNT matches $EXPECTED_SLIDES"
else
    log_check WARN "V4z slide count (ZIP)" "$ZIP_SLIDE_COUNT zip XML vs $EXPECTED_SLIDES expected (pdfinfo is authoritative)"
fi

# V7z blank-slide heuristic via XML size (always runs)
TMP_SLIDES=$(mktemp -d)
unzip -q "$PPTX_FILE" 'ppt/slides/slide*.xml' -d "$TMP_SLIDES" 2>/dev/null || true
if [[ -d "$TMP_SLIDES/ppt/slides" ]]; then
    SUSPICIOUS=0
    for xml in "$TMP_SLIDES"/ppt/slides/slide*.xml; do
        [[ -f "$xml" ]] || continue
        XML_SIZE=$(stat -c%s "$xml")
        # An empty-ish slide XML is typically < 1.5 KB (just the template frame)
        if [[ "$XML_SIZE" -lt 1500 ]]; then
            SUSPICIOUS=$((SUSPICIOUS+1))
        fi
    done
    if [[ "$SUSPICIOUS" -eq 0 ]]; then
        log_check PASS "V7z no sparse slide (XML)" "all slides > 1.5KB XML"
    else
        log_check WARN "V7z no sparse slide (XML)" "$SUSPICIOUS slides with < 1.5KB XML (possibly empty)"
    fi
fi
rm -rf "$TMP_SLIDES"

# V4-V8 only if PDF exists
if [[ -n "$PDF_FILE" && -f "$PDF_FILE" ]]; then
    # V4 slide count
    if command -v pdfinfo >/dev/null 2>&1; then
        ACTUAL=$(pdfinfo "$PDF_FILE" 2>/dev/null | awk '/^Pages:/ {print $2}')
        if [[ "$ACTUAL" == "$EXPECTED_SLIDES" ]]; then
            log_check PASS "V4 slide count" "$ACTUAL matches $EXPECTED_SLIDES"
        else
            log_check FAIL "V4 slide count" "$ACTUAL actual vs $EXPECTED_SLIDES expected"
        fi
    else
        log_check WARN "V4 slide count" "pdfinfo not installed"
    fi

    # V5 PDF size
    PDF_SIZE=$(stat -c%s "$PDF_FILE")
    if [[ "$PDF_SIZE" -gt 51200 ]]; then
        log_check PASS "V5 PDF size" "${PDF_SIZE} bytes"
    else
        log_check WARN "V5 PDF size" "${PDF_SIZE} bytes (< 50KB, possibly too sparse)"
    fi

    # V6 PNG rendering
    if command -v pdftoppm >/dev/null 2>&1; then
        pdftoppm -png -r 72 "$PDF_FILE" "${ART_DIR}/slide" 2>/dev/null || true
        PNG_COUNT=$(find "$ART_DIR" -maxdepth 1 -name 'slide-*.png' | wc -l)
        if [[ "$PNG_COUNT" -gt 0 ]]; then
            log_check PASS "V6 PNG rendering" "$PNG_COUNT PNGs created"
        else
            log_check FAIL "V6 PNG rendering" "zero PNGs"
        fi

        # V7 blank slide detection
        BLANK_COUNT=0
        for png in "${ART_DIR}"/slide-*.png; do
            [[ -f "$png" ]] || continue
            PNG_SIZE=$(stat -c%s "$png")
            if [[ "$PNG_SIZE" -lt 5120 ]]; then
                BLANK_COUNT=$((BLANK_COUNT+1))
            fi
        done
        if [[ "$BLANK_COUNT" -eq 0 ]]; then
            log_check PASS "V7 no blank slides" "all slides > 5KB"
        else
            log_check WARN "V7 no blank slides" "$BLANK_COUNT suspicious slides (< 5KB PNG)"
        fi
    else
        log_check WARN "V6 PNG rendering" "pdftoppm not installed"
    fi

    # V8 soffice warnings. Ignore benign javaldx warning emitted when Java
    # runtime is not installed (we never use Impress macros, so irrelevant).
    if [[ -f "$SOFFICE_LOG" ]]; then
        set +o pipefail
        WARN_COUNT=$(grep -iE "warning|error" "$SOFFICE_LOG" 2>/dev/null | grep -viE "javaldx|java may not function" 2>/dev/null | wc -l 2>/dev/null | tr -cd '0-9')
        set -o pipefail
        [[ -z "$WARN_COUNT" ]] && WARN_COUNT=0
        if [[ "${WARN_COUNT:-0}" == "0" ]]; then
            log_check PASS "V8 soffice clean" "no real warnings/errors (javaldx ignored)"
        else
            log_check WARN "V8 soffice clean" "$WARN_COUNT warning/error lines"
        fi
    fi
fi

# V11 deep-parse via python-pptx (always runs, no soffice needed)
DEEP_SCRIPT="$(dirname "$0")/pptx_deep_parse.py"
if command -v python3 >/dev/null 2>&1 && [[ -f "$DEEP_SCRIPT" ]]; then
    DEEP_OUT=$(python3 "$DEEP_SCRIPT" "$PPTX_FILE" 2>&1 || true)
    DEEP_SUMMARY=$(echo "$DEEP_OUT" | grep "^SUMMARY " | head -1)
    if [[ -n "$DEEP_SUMMARY" ]]; then
        SUSPICIOUS=$(echo "$DEEP_SUMMARY" | sed -nE 's/.*suspicious=([0-9]+).*/\1/p')
        NOCONTENT=$(echo "$DEEP_SUMMARY" | sed -nE 's/.*slides_no_content=([0-9]+).*/\1/p')
        EMPTYCH=$(echo "$DEEP_SUMMARY" | sed -nE 's/.*empty_charts=([0-9]+).*/\1/p')
        if [[ "${SUSPICIOUS:-0}" -eq 0 ]]; then
            log_check PASS "V11 deep parse (python-pptx)" "no_content=${NOCONTENT:-0} empty_charts=${EMPTYCH:-0}"
        else
            log_check WARN "V11 deep parse (python-pptx)" "suspicious=$SUSPICIOUS no_content=${NOCONTENT:-0} empty_charts=${EMPTYCH:-0}"
        fi
        # Save full per-slide breakdown to artifact dir
        echo "$DEEP_OUT" > "${ART_DIR}/deep_parse.txt"
    else
        log_check WARN "V11 deep parse (python-pptx)" "python-pptx unavailable or parse error"
    fi
fi

# V9 placeholder detection in raw XML
TMP_UNZIP=$(mktemp -d)
unzip -q "$PPTX_FILE" "ppt/slides/*.xml" -d "$TMP_UNZIP" 2>/dev/null || true
PLACEHOLDER_HITS=0
if [[ -d "$TMP_UNZIP/ppt/slides" ]]; then
    PLACEHOLDER_HITS=$(grep -riE '\{placeholder\}|TODO|FIXME|lorem ipsum|example\.com' "$TMP_UNZIP/ppt/slides/" 2>/dev/null | wc -l || true)
fi
rm -rf "$TMP_UNZIP"
if [[ "$PLACEHOLDER_HITS" -eq 0 ]]; then
    log_check PASS "V9 no placeholder" "zero literal placeholders"
else
    log_check FAIL "V9 no placeholder" "$PLACEHOLDER_HITS placeholder occurrences"
fi

# V10 aspect ratio sanity (if ImageMagick available + PNGs created)
if command -v identify >/dev/null 2>&1 && [[ -f "${ART_DIR}/slide-01.png" ]]; then
    DIMS=$(identify -format "%wx%h" "${ART_DIR}/slide-01.png" 2>/dev/null || echo "0x0")
    W=${DIMS%x*}
    H=${DIMS#*x}
    if [[ "$H" -gt 0 ]]; then
        RATIO=$(awk "BEGIN { printf \"%.2f\", $W/$H }")
        if awk "BEGIN { exit !($RATIO > 1.72 && $RATIO < 1.82) }"; then
            log_check PASS "V10 aspect 16:9" "$RATIO"
        else
            log_check WARN "V10 aspect 16:9" "$RATIO (outside 1.72-1.82)"
        fi
    fi
fi

# Summary + verdict
{
    echo
    echo "## Summary"
    echo
    echo "- PASS: $PASS"
    echo "- WARN: $WARN"
    echo "- FAIL: $FAIL"
    echo
} >> "$REPORT"

if [[ "$FAIL" -gt 0 ]]; then
    VERDICT="FAILURE"
    EXIT=2
elif [[ "$WARN" -gt 0 ]]; then
    VERDICT="PARTIAL"
    EXIT=1
else
    VERDICT="SUCCESS"
    EXIT=0
fi

echo "## Verdict: $VERDICT" >> "$REPORT"

echo "=== pptx-recette $VERDICT ==="
echo "Report: $REPORT"
echo "Artifacts: $ART_DIR"
exit "$EXIT"
