# Test Scripts, Sample Output, and Validation Gates

## test_collect.sh Template

```bash
#!/bin/bash
# =============================================================================
# Test script for Collect-{Technology}
# Validates the collection script output format and field presence.
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_NAME="Collect-{Technology}"
OUTPUT_FILE="${SCRIPT_DIR}/test_output_$(date +%Y%m%d_%H%M%S).json"

echo "=========================================="
echo "Testing: $SCRIPT_NAME"
echo "=========================================="
echo ""

# -----------------------------------------------------------------------
# STEP 1: Execute collection script
# -----------------------------------------------------------------------

echo "[STEP 1] Executing collection script..."

# PowerShell script:
# pwsh "${SCRIPT_DIR}/${SCRIPT_NAME}.ps1" -OutputPath "$OUTPUT_FILE" -Server "localhost"

# Bash script:
# bash "${SCRIPT_DIR}/${SCRIPT_NAME}.sh" "$OUTPUT_FILE" "localhost"

# Check if output was created
if [ ! -f "$OUTPUT_FILE" ]; then
    echo "  FAIL: Output file not created"
    exit 1
fi
echo "  PASS: Output file created ($OUTPUT_FILE)"

# -----------------------------------------------------------------------
# STEP 2: Validate JSON syntax
# -----------------------------------------------------------------------

echo ""
echo "[STEP 2] Validating JSON syntax..."
if jq . "$OUTPUT_FILE" > /dev/null 2>&1; then
    echo "  PASS: Valid JSON"
else
    echo "  FAIL: Invalid JSON"
    exit 1
fi

# -----------------------------------------------------------------------
# STEP 3: Check object count
# -----------------------------------------------------------------------

echo ""
echo "[STEP 3] Checking object count..."
OBJECT_COUNT=$(jq 'length' "$OUTPUT_FILE" 2>/dev/null || echo 0)
echo "  Objects collected: $OBJECT_COUNT"
if [ "$OBJECT_COUNT" -eq 0 ]; then
    echo "  WARN: No objects collected (script may need live target)"
fi

# -----------------------------------------------------------------------
# STEP 4: Validate required fields (CRITICAL)
# -----------------------------------------------------------------------

echo ""
echo "[STEP 4] Validating required fields..."

REQUIRED_FIELDS=("ObjectClass" "Hostname" "Version" "CollectionDate")
PASS_COUNT=0
FAIL_COUNT=0

for field in "${REQUIRED_FIELDS[@]}"; do
    if jq -e ".[0].$field" "$OUTPUT_FILE" > /dev/null 2>&1; then
        echo "  PASS: Field '$field' present"
        PASS_COUNT=$((PASS_COUNT + 1))
    else
        echo "  FAIL: Field '$field' MISSING"
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
done

# -----------------------------------------------------------------------
# STEP 5: Validate MOTOR_FIX_010 compliance
# -----------------------------------------------------------------------

echo ""
echo "[STEP 5] Checking MOTOR_FIX_010 compliance..."

FORBIDDEN_FIELDS=("is_compliant" "is_vulnerable" "is_affected" "is_patched" "check_result")
MF010_VIOLATIONS=0

for field in "${FORBIDDEN_FIELDS[@]}"; do
    if jq -e ".[0] | has(\"$field\")" "$OUTPUT_FILE" 2>/dev/null | grep -q "true"; then
        echo "  VIOLATION: Field '$field' detected (MOTOR_FIX_010)"
        MF010_VIOLATIONS=$((MF010_VIOLATIONS + 1))
    fi
done

# Also check for CVE_*_is_vulnerable pattern
CVE_FIELDS=$(jq -r '.[0] | keys[]' "$OUTPUT_FILE" 2>/dev/null | grep -iE 'CVE.*vulnerable|CVE.*affected|CVE.*patched' || true)
if [ -n "$CVE_FIELDS" ]; then
    echo "  VIOLATION: CVE detection fields found: $CVE_FIELDS"
    MF010_VIOLATIONS=$((MF010_VIOLATIONS + 1))
fi

if [ "$MF010_VIOLATIONS" -eq 0 ]; then
    echo "  PASS: No MOTOR_FIX_010 violations"
else
    echo "  FAIL: $MF010_VIOLATIONS MOTOR_FIX_010 violations detected"
fi

# -----------------------------------------------------------------------
# STEP 6: Validate ObjectClass naming
# -----------------------------------------------------------------------

echo ""
echo "[STEP 6] Checking ObjectClass values..."
OBJECT_CLASSES=$(jq -r '.[].ObjectClass' "$OUTPUT_FILE" 2>/dev/null | sort -u)
echo "  ObjectClass values found:"
echo "$OBJECT_CLASSES" | while read -r oc; do
    OC_COUNT=$(jq "[.[] | select(.ObjectClass == \"$oc\")] | length" "$OUTPUT_FILE" 2>/dev/null)
    echo "    - $oc ($OC_COUNT objects)"
done

# -----------------------------------------------------------------------
# STEP 7: Check for mock/placeholder data
# -----------------------------------------------------------------------

echo ""
echo "[STEP 7] Checking for mock/placeholder data..."

# Check for exact mock values
MOCK_COUNT=$(jq '[.[] | .. | select(type == "string" and (. == "mock" or . == "test" or . == "example" or . == "dummy" or . == "placeholder" or . == "TODO" or . == "changeme"))] | length' "$OUTPUT_FILE" 2>/dev/null || echo 0)
if [ "$MOCK_COUNT" -eq 0 ]; then
    echo "  PASS: No mock/placeholder values"
else
    echo "  FAIL: $MOCK_COUNT mock/placeholder values detected"
fi

# Check for documentation IPs (RFC 5737)
DOC_IP_COUNT=$(jq -r '.[].Hostname // empty, .[].IP // empty, .[].Server // empty' "$OUTPUT_FILE" 2>/dev/null | grep -cE '192\.0\.2\.|198\.51\.100\.|203\.0\.113\.' || echo 0)
if [ "$DOC_IP_COUNT" -eq 0 ]; then
    echo "  PASS: No RFC 5737 documentation IPs"
else
    echo "  FAIL: $DOC_IP_COUNT documentation IPs detected"
fi

# -----------------------------------------------------------------------
# SUMMARY
# -----------------------------------------------------------------------

echo ""
echo "=========================================="
echo "SUMMARY"
echo "=========================================="
echo "  Objects collected:      $OBJECT_COUNT"
echo "  Required fields:        $PASS_COUNT/$((PASS_COUNT + FAIL_COUNT)) PASS"
echo "  MOTOR_FIX_010:          $( [ $MF010_VIOLATIONS -eq 0 ] && echo 'COMPLIANT' || echo 'VIOLATED' )"
echo "  Mock data:              $( [ $MOCK_COUNT -eq 0 ] && echo 'CLEAN' || echo 'DETECTED' )"

TOTAL_ISSUES=$((FAIL_COUNT + MF010_VIOLATIONS + MOCK_COUNT + DOC_IP_COUNT))
if [ "$TOTAL_ISSUES" -eq 0 ]; then
    echo ""
    echo "  VERDICT: PASS - Script output is valid"
    exit 0
elif [ "$MF010_VIOLATIONS" -gt 0 ]; then
    echo ""
    echo "  VERDICT: CRITICAL FAIL - MOTOR_FIX_010 violations"
    exit 1
else
    echo ""
    echo "  VERDICT: PARTIAL - $TOTAL_ISSUES issues to fix"
    exit 2
fi
```

## sample_output.json Template

```json
[
  {
    "ObjectClass": "{technology_lowercase}_instance",
    "Hostname": "{realistic-hostname-1}.{real-domain}.net",
    "Version": "{real_version_1}",
    "Product": "{Technology}",
    "CollectionDate": "2026-02-15T10:30:00Z",
    "CollectorVersion": "1.0.0"
  },
  {
    "ObjectClass": "{technology_lowercase}_instance",
    "Hostname": "{realistic-hostname-2}.{real-domain}.net",
    "Version": "{real_version_2}",
    "Product": "{Technology}",
    "CollectionDate": "2026-02-15T10:31:00Z",
    "CollectorVersion": "1.0.0"
  },
  {
    "ObjectClass": "{technology_lowercase}_instance",
    "Hostname": "{realistic-hostname-3}.{real-domain}.net",
    "Version": "{real_version_3}",
    "Product": "{Technology}",
    "CollectionDate": "2026-02-15T10:32:00Z",
    "CollectorVersion": "1.0.0"
  }
]
```

Rules for sample_output.json:
- Minimum 2-3 representative objects
- REAL product versions (not invented)
- Realistic hostnames (not corp.local, example.com, contoso.com)
- No RFC 5737 IPs (192.0.2.x, 198.51.100.x, 203.0.113.x)
- Must pass jq validation
- Reflect EXACTLY the fields the collection script produces

## OBJECTCLASS_REFERENCE.md Template

```markdown
# ObjectClass Reference - {Technology}

## Script: Collect-{Technology}.ps1 (or .sh)

### ObjectClass: {technology_lowercase}_instance

**Description:** Information about {Technology} instances/servers.

**Available fields:**
| Field | Type | Description | Example |
|-------|------|-------------|---------|
| ObjectClass | string | Object type (fixed) | "{technology_lowercase}_instance" |
| Hostname | string | Server name | "srv-prod-01.corp.local" |
| Version | string | Full version | "17.3.0" |
| VersionNormalized | string | Normalized version | "17.3.0" |
| MajorVersion | string | Major version | "17" |
| MinorVersion | string | Minor version | "3" |
| Product | string | Product name | "{Technology}" |
| CollectionDate | string | Collection date ISO 8601 | "2026-02-15T10:30:00Z" |
| CollectorVersion | string | Script version | "1.0.0" |

### Usage in YAML rules:

    object_detection:
      match:
        ObjectClass:
          eq: "{technology_lowercase}_instance"
      where:
        condition: and
        rules:
          - ObjectClass:
              eq: "{technology_lowercase}_instance"
          - Version:
              version_lt: "X.Y.Z"

    output:
      fields:
        Hostname: Hostname
        Version: Version
        MajorVersion: MajorVersion
        Product: Product
```

## COLLECTION_RESEARCH.md Template

```markdown
# Collection Research - {TECHNOLOGY}

## Date: YYYY-MM-DD

## Search Queries and Results

### Query 1: "{technology} powershell cmdlets"
- Result: [Description]
- URL: [URL source]
- Useful: Yes/No

### Query 2: "{technology} REST API endpoints"
- Result: [Description]
- URL: [URL source]
- Useful: Yes/No

### Query 3: "{technology} CLI version check"
- Result: [Description]
- URL: [URL source]
- Useful: Yes/No

### Query 4: "{technology} security configuration"
- Result: [Description]
- URL: [URL source]
- Useful: Yes/No

## Discovered Collection Methods

### Primary Method: {PowerShell/Bash/API}
- **Tool:** {cmdlet/CLI/endpoint}
- **Command:** {exact command}
- **Authentication:** {method}
- **Pre-requisites:** {modules, packages}
- **Output format:** {JSON, text, etc.}

### Available Data Points
| Field Name | Source | Type | Example Value |
|------------|--------|------|---------------|
| Version | {command} | string | "17.3.0" |
| Hostname | {command} | string | "srv-prod-01" |

## Proposed ObjectClass Names
- {technology_lowercase}_instance - For instances/servers
- {technology_lowercase}_config - For configuration
- {technology_lowercase}_security - For security settings

## Source URLs
1. [Official documentation](URL)
2. [API Reference](URL)
3. [PowerShell Module](URL)
```

## Validation Gates (BLOCKING - before declaring "done")

```bash
# Gate 1: Zero placeholder in scripts
grep -rn '\{[A-Za-z_]+\}' scripts/collect/{tech}/*.ps1 scripts/collect/{tech}/*.sh 2>/dev/null
# -> MUST return zero results

# Gate 2: Zero MOTOR_FIX_010 violations
grep -rn 'is_compliant\|is_vulnerable\|CVE.*_is_' scripts/collect/{tech}/*.ps1 scripts/collect/{tech}/*.sh 2>/dev/null
# -> MUST return zero results

# Gate 3: COLLECTION_RESEARCH.md with real URLs
URL_COUNT=$(grep -oE 'https?://[^ ]+' scripts/collect/{tech}/COLLECTION_RESEARCH.md 2>/dev/null | wc -l)
echo "URLs found: $URL_COUNT (minimum 3 required)"

# Gate 4: sample_output.json valid
jq 'length' scripts/collect/{tech}/sample_output.json 2>/dev/null
# -> MUST return >= 2

# Gate 5: No RFC 5737 fictitious values in sample_output
grep -E '192\.0\.2\.|198\.51\.100\.|203\.0\.113\.' scripts/collect/{tech}/sample_output.json 2>/dev/null
# -> MUST return zero results
```

If ANY gate fails: STOP -> return to Phase 0 -> correct -> re-gate.
