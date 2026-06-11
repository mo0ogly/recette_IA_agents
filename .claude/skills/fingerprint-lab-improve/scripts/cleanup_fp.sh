#!/bin/bash
# Desactive tous les patterns FP recurrents connus dans les 3 emplacements
# Usage: cleanup_fp.sh [--verify PORT]
set -euo pipefail

BASE="/opt/lia-sec/dev"

# FP recurrents connus (mis a jour via RETEX)
LIA_FP=(TRNAS RNCHR MATMO PLAUS ONVIF)
NUCLEI_FP=(
    DETECT_REDMINE_CLI_CONFIGURATION_FILE
    KUBELET_HEALTHZ KUBELET_STATS KUBELET_SCAN KUBELET_RUNNING_PODS
    JIRA_REST_API_SERVER_INFORMATION
    NACOS TYK_API_GATEWAY MATRIX_HOMESERVER COUCHDB
    WAF_DETECTION FINGERPRINTHUB_TECHNOLOGY_FINGERPRINT
    APACHE_AXIS SYMFONY_DEFAULT_PAGE
    CITRIX_XENMOBILE_VERSION OQTANE_CMS_DATABASE
    TORCHSERVE_API_DESCRIPTION METATAG_CMS_DETECTION
)

disable_pattern() {
    local f="$1"
    if [ -f "$f" ]; then
        python3 -c "import json; d=json.load(open('$f')); d['enabled']=False; json.dump(d,open('$f','w'),indent=2)" 2>/dev/null
        echo "  disabled: $(basename $f)"
    fi
}

echo "=== Cleanup FP recurrents ==="

echo "[lia/]"
for taxo in "${LIA_FP[@]}"; do
    disable_pattern "$BASE/data/fingerprints/lia/$taxo.json"
done

echo "[nuclei/]"
for taxo in "${NUCLEI_FP[@]}"; do
    disable_pattern "$BASE/data/fingerprints/nuclei/$taxo.json"
done

echo "[by-taxonomy/]"
for taxo in "${LIA_FP[@]}" "${NUCLEI_FP[@]}"; do
    for f in $(find "$BASE/data/fingerprints/by-taxonomy" -name "${taxo}*.json" 2>/dev/null); do
        disable_pattern "$f"
    done
done

echo "[sync -> liaprobe/]"
rsync -a "$BASE/data/fingerprints/by-taxonomy/" "$BASE/liaprobe/data/fingerprints/by-taxonomy/" 2>/dev/null
echo "  synced"

# Verification optionnelle
if [ "${1:-}" = "--verify" ] && [ -n "${2:-}" ]; then
    PORT="$2"
    echo ""
    echo "=== Verification sur port $PORT ==="
    cd "$BASE/liaprobe" && make build 2>&1 | tail -1
    cd "$BASE"
    ALL_FP=("${LIA_FP[@]}" "${NUCLEI_FP[@]}")
    FAIL_COUNT=0
    timeout 30 ./liaprobe/bin/liaprobe --mode specific --ports "$PORT" 127.0.0.1 2>/dev/null | \
        grep '"pattern_id"' | while read line; do
            pat=$(echo "$line" | grep -o '"[^"]*"$' | tr -d '"')
            for fp in "${ALL_FP[@]}"; do
                if echo "$pat" | grep -qi "$fp"; then
                    echo "  FAIL: FP still active: $pat"
                    FAIL_COUNT=$((FAIL_COUNT + 1))
                fi
            done
        done
    if [ "$FAIL_COUNT" -eq 0 ]; then
        echo "  OK: 0 FP connus detectes"
    fi
    echo "  verification done"
fi

echo ""
echo "Total: ${#LIA_FP[@]} lia + ${#NUCLEI_FP[@]} nuclei FP desactives"
