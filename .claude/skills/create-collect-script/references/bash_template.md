# Bash Collection Script Template

## Full Template

```bash
#!/bin/bash
# =============================================================================
# Collect-{Technology}.sh - LIA-Scan Collection Script
# =============================================================================
#
# Collects raw data from {Technology} for LIA-Scan analysis.
#
# ObjectClass(es): {technology_lowercase}_instance, {technology_lowercase}_config
# Collection method: {CLI commands / config files / API}
# Source: {URL from research}
#
# MOTOR_FIX_010 COMPLIANT: Raw data only, no detection logic.
#
# Usage:
#   ./Collect-{Technology}.sh [output_file] [server] [port]
#
# Author: LIA-Scan Platform
# Version: 1.0.0
# Date: {YYYY-MM-DD}
# Research: See COLLECTION_RESEARCH.md
# =============================================================================

set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_FILE="${1:-${SCRIPT_DIR}/output_$(date +%Y%m%d_%H%M%S).json}"
SERVER="${2:-localhost}"
# Real default port of the technology - replace per COLLECTION_RESEARCH.md
PORT="${3:-443}"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
COLLECTOR_VERSION="1.0.0"

# ============================================================================
# HELPERS
# ============================================================================

json_escape() {
    local str="$1"
    str="${str//\\/\\\\}"
    str="${str//\"/\\\"}"
    str="${str//$'\n'/\\n}"
    str="${str//$'\r'/}"
    str="${str//$'\t'/\\t}"
    echo "$str"
}

FIRST_ENTRY=true
json_start() {
    echo "[" > "$OUTPUT_FILE"
    FIRST_ENTRY=true
}

json_add() {
    if [ "$FIRST_ENTRY" = true ]; then
        FIRST_ENTRY=false
    else
        echo "," >> "$OUTPUT_FILE"
    fi
    echo "$1" >> "$OUTPUT_FILE"
}

json_end() {
    echo "" >> "$OUTPUT_FILE"
    echo "]" >> "$OUTPUT_FILE"
}

log() {
    echo "[$(date +%H:%M:%S)] $1" >&2
}

# ============================================================================
# MAIN COLLECTION
# ============================================================================

log "Starting {Technology} collection from $SERVER:$PORT"

json_start

OBJECT_COUNT=0
ERROR_COUNT=0

# -----------------------------------------------------------------------
# COLLECT RAW DATA (real commands from Phase 0 + WebSearch)
# -----------------------------------------------------------------------
# Implement HERE the commands found in Phase 0.
# Each command must have a source URL in COLLECTION_RESEARCH.md.
# NO "TODO" comments or invented values in the final deliverable.
#
# Reference patterns (adapt per technology):
#
# Pattern version from package manager:
#   version=$(dpkg-query -W -f='${Version}' nginx 2>/dev/null || apt-cache show nginx 2>/dev/null | grep "^Version:" | head -1 | cut -d' ' -f2)
#
# Pattern systemd service:
#   is_enabled=$(systemctl is-enabled nginx 2>/dev/null || echo "unknown")
#   is_active=$(systemctl is-active nginx 2>/dev/null || echo "unknown")
#
# Pattern configuration file:
#   config_value=$(grep -E "^ssl_protocols" /etc/nginx/nginx.conf 2>/dev/null | awk '{print $2}')
#
# Pattern local REST API:
#   api_response=$(curl -s -k -H "Authorization: Bearer ${API_TOKEN}" "https://$SERVER:$PORT/api/v1/status" 2>&1)
#   version=$(echo "$api_response" | jq -r '.version // "unknown"' 2>/dev/null || echo "unknown")

# BUILD OUTPUT (RAW DATA ONLY - NO CVE DETECTION LOGIC)
# json_add "$(jq -n \
#     --arg oc "nginx_instance" \
#     --arg host "$SERVER" \
#     --arg ver "$version" \
#     --arg major "${version%%.*}" \
#     --arg ts "$TIMESTAMP" \
#     --arg cv "$COLLECTOR_VERSION" \
#     '{
#         ObjectClass: $oc,
#         Hostname: $host,
#         Version: $ver,
#         MajorVersion: $major,
#         Product: "Nginx",
#         CollectionDate: $ts,
#         CollectorVersion: $cv
#     }')"
# OBJECT_COUNT=$((OBJECT_COUNT + 1))

json_end

# ============================================================================
# SUMMARY
# ============================================================================

log "Collection complete: $OBJECT_COUNT objects, $ERROR_COUNT errors"
log "Output: $OUTPUT_FILE"

# Validate JSON
if jq . "$OUTPUT_FILE" > /dev/null 2>&1; then
    log "JSON validation: PASS"
else
    log "JSON validation: FAIL"
    exit 1
fi
```

## Bash Collection Patterns

### Package Manager Version

```bash
version=$(dpkg-query -W -f='${Version}' nginx 2>/dev/null || echo "unknown")
```

### Systemd Service Status

```bash
is_enabled=$(systemctl is-enabled nginx 2>/dev/null || echo "unknown")
is_active=$(systemctl is-active nginx 2>/dev/null || echo "unknown")
```

### Configuration File Parsing

```bash
config_value=$(grep -E "^ssl_protocols" /etc/nginx/nginx.conf 2>/dev/null | awk '{print $2}')
```

### REST API Call

```bash
api_response=$(curl -s -k -H "Authorization: Bearer ${API_TOKEN}" "https://$SERVER:$PORT/api/v1/status" 2>&1)
version=$(echo "$api_response" | jq -r '.version // "unknown"' 2>/dev/null || echo "unknown")
```

### CIS Compliance Check (sysctl)

```bash
sysctl_value=$(sysctl -n net.ipv4.conf.all.accept_redirects 2>/dev/null || echo "unknown")
```

---

## BLOQUANT -- Two traps that make a collector hang or emit nothing

Incident 2026-05-29 (SANDBOXJS CVE-2026-43898 nightly harvest): the generated
`Collect-NodeJS-Apps.sh` (a) scanned `/opt /home ...` `-maxdepth 6` and spawned 4-5
`python3` per `package.json` (tens of thousands of processes on a node_modules-heavy
box) -> the recette `test_collect_script.sh` timed out (rc=124), failing the whole rule;
and (b) accumulated results inside a `find | while ...; RESULTS+=...; done` pipeline ->
the `while` ran in a SUBSHELL so every `RESULTS`/`FIRST` mutation was lost -> empty
output regardless. Both must be avoided in every filesystem-walking collector.

### Trap 1 -- subshell variable loss (`cmd | while`)

```bash
# FORBIDDEN -- the while runs in a subshell; RESULTS is empty after the loop
RESULTS="["
find "$root" -name package.json | while read -r f; do
    RESULTS+="...$f..."   # lost: subshell scope
done
echo "$RESULTS]" > out.json   # always just "[]"
```

```bash
# CORRECT -- process substitution keeps the loop in the current shell
RESULTS="["
while IFS= read -r f; do
    RESULTS+="...$f..."
done < <(find "$root" -name package.json)
echo "$RESULTS]" > out.json
# Or better: skip the shell accumulation entirely (Trap 2).
```

### Trap 2 -- one interpreter spawn per file (perf cliff)

```bash
# FORBIDDEN -- 4-5 python3/jq per file x thousands of files = recette timeout
find "$root" -name package.json | while read -r f; do
    name=$(python3 -c "import json;print(json.load(open('$f'))['name'])")
    ver=$(python3 -c "import json;print(json.load(open('$f'))['version'])")
    ...
done
```

```bash
# CORRECT -- feed ALL paths to ONE interpreter pass (no per-file spawn, no subshell)
find "$root" -name package.json ! -path "*/node_modules/*/node_modules/*" 2>/dev/null \
  | python3 -c '
import json,sys,os
out=[]
for line in sys.stdin:
    p=line.strip()
    if not p: continue
    try: d=json.load(open(p))
    except Exception: continue
    out.append({"ObjectClass":"...","name":d.get("name",""),"version":d.get("version","")})
json.dump(out, sys.stdout)' > "$OUTPUT_FILE"
```

### Bound the scan + make it testable

```bash
# Scan roots overridable so the recette test runs against a bounded fixture, NOT all of /.
# Default roots EXCLUDE the platform tree itself (/opt/lia-sec) to avoid its bundled node_modules.
SCAN_PATHS="${LIA_<TECH>_SCAN_PATHS:-/srv /var/www /app /apps /deploy}"
MAX_DEPTH="${LIA_<TECH>_MAX_DEPTH:-6}"
```

Verify in `test_collect_script.sh`: a bounded default run must finish in < 1s and emit
VALID JSON (empty array `[]` is valid), and a fixture run must emit real rows. Otherwise
the recette `Script de collecte genere JSON valide` check is a HIGH and the harvest times out.
