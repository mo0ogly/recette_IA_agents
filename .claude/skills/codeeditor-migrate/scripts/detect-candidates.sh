#!/usr/bin/env bash
# detect-candidates.sh -- Scan a .tsx file for <TextField multiline rows={N>=6}>
# and emit a tab-separated report of migration candidates for CodeEditor.
#
# Usage:
#   detect-candidates.sh <path/to/File.tsx>
#
# Output columns (tab-separated):
#   line_start  rows  inferred_language  nearby_hint  suggested_height
#
# Inferred language heuristics (looks in the 15 lines around each candidate):
#   yaml       if yaml.dump|yaml.load present
#   json       if JSON.stringify|JSON.parse present
#   markdown   if "markdown" or "body" or ".md" or placeholder starts with "#"
#   plaintext  otherwise
#
# Exit codes:
#   0 -- candidates found (or zero, still success)
#   1 -- usage error / file not readable

set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 <path/to/File.tsx>" >&2
    exit 1
fi

FILE="$1"

if [[ ! -r "$FILE" ]]; then
    echo "ERROR: cannot read $FILE" >&2
    exit 1
fi

# Print header
printf "line_start\trows\tlanguage\tsignal\theight_px\n"

# Find every line with "rows={N}" where N is numeric, then for each check
# the preceding 5 lines for "<TextField" with "multiline" before it.
#
# grep -nE captures line_number:content. Awk collects context via a small
# buffer of the last 10 lines.

awk -v file="$FILE" '
function max(a, b) { return (a > b ? a : b) }
{
    # Keep a rolling buffer of the last 15 lines for context
    buf[NR] = $0
}
END {
    for (n = 1; n <= NR; n++) {
        line = buf[n]
        if (line !~ /rows=\{[0-9]+\}/) continue
        # Extract N from rows={N}
        split(line, m, /rows=\{|\}/)
        rows = m[2] + 0
        if (rows < 6) continue
        # Look back up to 5 lines for "<TextField" with "multiline"
        has_tf = 0
        for (i = max(1, n - 5); i < n; i++) {
            if (buf[i] ~ /<TextField/) {
                # Check multiline is present in the window
                for (j = i; j <= n; j++) {
                    if (buf[j] ~ /multiline/) { has_tf = 1 ; break }
                }
                if (has_tf) break
            }
        }
        if (!has_tf) continue

        # Collect 15 surrounding lines for language inference
        ctx = ""
        for (i = max(1, n - 7); i <= n + 7 && i <= NR; i++) {
            ctx = ctx " " buf[i]
        }
        lang = "plaintext"
        signal = "default"
        if (ctx ~ /yaml\.dump|yaml\.load/) { lang = "yaml"; signal = "yaml.dump|yaml.load" }
        else if (ctx ~ /JSON\.stringify|JSON\.parse/) { lang = "json"; signal = "JSON.stringify|JSON.parse" }
        else if (ctx ~ /markdown|body|\.md|Markdown/) { lang = "markdown"; signal = "markdown-hint" }

        # Find line start of the TextField block
        for (i = max(1, n - 5); i < n; i++) {
            if (buf[i] ~ /<TextField/) { tf_line = i ; break }
        }

        # Height : rows * 26 + 10
        height = rows * 26 + 10

        printf "%d\t%d\t%s\t%s\t%d\n", tf_line, rows, lang, signal, height
    }
}
' "$FILE"
