#!/bin/bash
# check_hardcodings.sh - Detecte les hardcodings dans code ET commentaires
# Usage: ./check_hardcodings.sh <file_path>
# Exit: 0=OK, 1=violations trouvees

FILE="$1"
if [[ -z "$FILE" || ! -f "$FILE" ]]; then
    echo "Usage: $0 <file_path>" >&2
    exit 2
fi

ext="${FILE##*.}"
VIOLATIONS=0
MESSAGES=()

is_comment_go()  { echo "$1" | grep -qE '^\s*(//|\*|/\*|\*/)' ; }
is_comment_ts()  { echo "$1" | grep -qE '^\s*(//|\*|/\*|\*/)' ; }
is_comment_py()  { echo "$1" | grep -qE '^\s*#' ; }
is_import_go()   { echo "$1" | grep -qE '^\s*import' ; }
is_import_py()   { echo "$1" | grep -qE '^\s*(import|from)\s' ; }
is_official_url(){ echo "$1" | grep -qE 'nvd\.nist\.gov|cisa\.gov|attack\.mitre\.org' ; }
# Default value in a config service call is a valid pattern (R5), not a hardcoding violation
is_config_default_go() { echo "$1" | grep -qE 'GetSystemVarWithDefault\(|GetEnvWithDefault\(|os\.Getenv\(' ; }

add_violation() {
    local line_num="$1" tag="$2" msg="$3" content="$4"
    MESSAGES+=("  [$tag] ligne $line_num: $msg")
    MESSAGES+=("    $content")
    ((VIOLATIONS++)) || true
}

# ============================================================
# PATTERNS GO
# ============================================================
if [[ "$ext" == "go" ]]; then

    while IFS=: read -r line_num content; do
        is_import_go "$content" && continue
        is_config_default_go "$content" && continue  # skip: default value in config service call is valid
        is_comment_go "$content" \
            && add_violation "$line_num" "COMMENT" "Port hardcode dans commentaire -> utiliser getCVEWorkerURL()" "$content" \
            || add_violation "$line_num" "HARDCODE" "localhost hardcode -> utiliser getCVEWorkerURL()" "$content"
    done < <(grep -n 'localhost:[0-9]\+\|127\.0\.0\.1:[0-9]\+' "$FILE" 2>/dev/null)

    while IFS=: read -r line_num content; do
        is_comment_go "$content" && continue
        echo "$content" | grep -qE 'localhost:|127\.0\.0\.1:' && continue  # deja vu
        add_violation "$line_num" "HARDCODE" "URL hardcodee -> externaliser via env/config" "$content"
    done < <(grep -n '"https\?://[^"]*"' "$FILE" 2>/dev/null)

    while IFS=: read -r line_num content; do
        is_comment_go "$content" && continue
        add_violation "$line_num" "LOGGER" "fmt.Println/Printf interdit -> utiliser LogSystemEvent()" "$content"
    done < <(grep -n 'fmt\.Print' "$FILE" 2>/dev/null)

fi

# ============================================================
# PATTERNS TS/TSX
# ============================================================
if [[ "$ext" == "ts" || "$ext" == "tsx" ]]; then

    while IFS=: read -r line_num content; do
        is_comment_ts "$content" \
            && add_violation "$line_num" "COMMENT" "Port hardcode dans commentaire -> utiliser getBackendUrl()" "$content" \
            || add_violation "$line_num" "HARDCODE" "localhost hardcode -> utiliser getBackendUrl() de ConfigurationService" "$content"
    done < <(grep -n 'localhost:[0-9]\+\|127\.0\.0\.1:[0-9]\+' "$FILE" 2>/dev/null)

    while IFS=: read -r line_num content; do
        is_comment_ts "$content" && continue
        echo "$content" | grep -qE 'localhost:|127\.0\.0\.1:' && continue
        # Skip SVG/XML namespace attributes and W3C standard URLs (not API endpoints)
        echo "$content" | grep -qE 'xmlns[^=]*=|http://www\.w3\.org/|xlink:href' && continue
        add_violation "$line_num" "HARDCODE" "URL hardcodee -> utiliser getBackendUrl() de ConfigurationService" "$content"
    done < <(grep -n "const.*URL.*=.*['\"]http\|['\"]https\?://[^'\"]*['\"]" "$FILE" 2>/dev/null)

    while IFS=: read -r line_num content; do
        is_comment_ts "$content" && continue
        add_violation "$line_num" "LOGGER" "console.log/error/warn interdit -> utiliser customLogger" "$content"
    done < <(grep -n 'console\.\(log\|error\|warn\|debug\)' "$FILE" 2>/dev/null)

fi

# ============================================================
# PATTERNS PYTHON
# ============================================================
if [[ "$ext" == "py" ]]; then

    while IFS=: read -r line_num content; do
        is_import_py "$content" && continue
        is_comment_py "$content" \
            && add_violation "$line_num" "COMMENT" "Port hardcode dans commentaire -> utiliser os.getenv() ou config" "$content" \
            || add_violation "$line_num" "HARDCODE" "localhost hardcode -> utiliser os.getenv() ou config" "$content"
    done < <(grep -n 'localhost:[0-9]\+\|127\.0\.0\.1:[0-9]\+' "$FILE" 2>/dev/null)

    while IFS=: read -r line_num content; do
        is_comment_py "$content" && continue
        is_official_url "$content" && continue
        echo "$content" | grep -qE 'localhost:|127\.0\.0\.1:' && continue  # deja vu
        add_violation "$line_num" "HARDCODE" "URL hardcodee -> utiliser os.getenv() ou config" "$content"
    done < <(grep -n "['\"]https\?://[^'\"]*['\"]" "$FILE" 2>/dev/null)

    while IFS=: read -r line_num content; do
        is_comment_py "$content" && continue
        add_violation "$line_num" "LOGGER" "print() interdit -> utiliser logging.info/error/warning()" "$content"
    done < <(grep -n '\bprint(' "$FILE" 2>/dev/null)

fi

# ============================================================
# RAPPORT
# ============================================================
if [[ "$VIOLATIONS" -gt 0 ]]; then
    echo "HARDCODING CHECK: $VIOLATIONS violation(s) dans $(basename "$FILE")"
    for msg in "${MESSAGES[@]}"; do echo "$msg"; done
    exit 1
fi

echo "HARDCODING CHECK: OK - $(basename "$FILE")"
exit 0
