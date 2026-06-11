# Collection Phase -- Directory Layout, Required Files, and Script Output

## Canonical storage root (source: path_utils.go GetCollectPath())

```
collect/                          # root = GetCollectPath() = project_base/collect/
                                  # (overridable via system_variables.COLLECT_PATH)
  {QUADRIGRAMME}/                 # e.g. ADDS, DOCK, LINX, PGSQ, K8SL
    {YYYYMMDD}/                   # campaign_date, e.g. 20260422
      collect/                    # RAW input: XMLs, ZIPs, JSONs uploaded or written by scripts
      prepare/                    # Prepared/pre-processed data (after preparation step)
      analyse/                    # Analysis outputs
        stats/                    # Statistical summaries
        results/                  # Main analysis results (analysis_results.json written here)
        logs/                     # Engine execution logs
        rules_results/            # Per-rule match results
      report/                     # Generated reports (PPTX, DOCX, PDF)
      display/                    # Display data for UI rendering
      compliance/                 # Compliance framework outputs
```

This structure is created by `EnsureCampaignDirectoryStructure(campaignID, date string)` in
`cmd/sigma_web/path_utils.go` (line 93+). It MUST be created via
`POST /api/campaigns/create-structure` BEFORE any collection script runs (see Phase 0 in SKILL.md).

**There is NO product-level subdirectory.** Each (QUAD, DATE) pair is a campaign unit.
Multiple products (docker, linux, postgres, k8s) collect into the SAME `collect/` subdirectory
within that campaign — distinguished by filename, not by folder.

---

## Required files (blocking — engine and merge will fail without them)

| Phase | File | Location | Written by |
|-------|------|----------|-----------|
| After COLLECTION | XMLs / JSONs / ZIPs from scripts | `collect/{QUAD}/{DATE}/collect/` | Collection scripts |
| After ANALYSIS | `analysis_results.json` | `collect/{QUAD}/{DATE}/analyse/results/` | `ExecuteRealAnalysis()` |
| After ANALYSIS | `analysis_{id}.log` | `_alire/temp/` (transient) | `ExecuteRealAnalysis()` |
| After MERGE | `result.json` | `_alire/temp/campaign-orchestrator/{slug}/merge/` | Orchestrator |
| After REPORTING | `{QUAD}_{DATE}.pptx` | `_alire/temp/campaign-orchestrator/{slug}/reports/` | `/api/export/professional` |

**The `collect/` subdirectory** (not the root) is where collection scripts MUST write their output.
The analysis engine resolves the collection path as `../../collect/{collectionID}` relative to the
binary, or accepts an absolute path if `collection_id` is absolute.

---

## Step 0 (BLOCKING): create directory structure before collection

```bash
QUAD="{QUADRIGRAMME}"
DATE="{YYYYMMDD}"

CREATE_RESP=$(curl -s -X POST \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${LIA_API_TOKEN}" \
  -d "{\"quadrigramme\":\"${QUAD}\",\"date\":\"${DATE}\"}" \
  http://localhost:8081/api/campaigns/create-structure)

# Verify success
echo "${CREATE_RESP}" | jq -e '.success == true' || {
  echo "ERROR: create-structure failed: $(echo ${CREATE_RESP} | jq -r '.error')"
  exit 2
}

# Confirm on disk
COLLECT_BASE=$(PGPASSWORD="$LIA_DB_PASS" psql -h localhost -U lia_admin -d lia_scan \
  -tAc "SELECT value FROM system_variables WHERE key = 'COLLECT_PATH' LIMIT 1")
COLLECT_BASE="${COLLECT_BASE:-/opt/lia-sec/dev/collect}"
CAMPAIGN_ROOT="${COLLECT_BASE}/${QUAD}/${DATE}"

for d in collect prepare analyse/stats analyse/results analyse/logs analyse/rules_results report display compliance; do
  test -d "${CAMPAIGN_ROOT}/${d}" || { echo "MISSING dir: ${CAMPAIGN_ROOT}/${d}"; exit 2; }
done
```

---

## Product -> script mapping

Verified on 2026-04-23 (present in `/opt/lia-sec/dev/scripts/collect/`):

| Product | Script (preferred) | Output interface | Output format |
|---------|--------------------|-----------------|---------------|
| `docker` | `scripts/collect/docker/Collect-Docker.sh` | `$1` = output FILE path | JSON |
| `linux` | `scripts/collect/linux/collect_linux_all.sh` | `$1` = output DIRECTORY path (creates `DATA_Linux_{ts}/` inside) | XML + JSON |
| `postgres` | `scripts/collect/postgresql/Collect-PostgreSQL.sh` | `$1` = output FILE path | JSON |
| `k8s` | `scripts/collect/kubernetes/Collect-Kubernetes.sh` | `$1` = output FILE path | JSON |
| `ub25` | `scripts/collect/ubuntu/Collect-Ubuntu-v3.sh` | `$1` = output DIRECTORY path | JSON (DATA_Ubuntu_CIS_{ts}/) |
| `go` | `scripts/collect/go/collect_go.sh` | `$1` = project dir to scan, writes JSON to CWD | JSON |
| `python` | `scripts/collect/python/collect_python.sh` | `$1` = output DIRECTORY path (writes `python_{ts}.json` inside) | JSON |

**Critical interface notes:**
- `docker`, `postgres`, `k8s`: pass the target file path as `$1` (e.g. `"${OUT}/docker_config.json"`)
- `linux`: pass `${OUT}` as `$1`; script creates `DATA_Linux_{ts}/` subdirectory inside it (unified 2026-04-23)
- `python`: pass `${OUT}` as `$1`; script writes `python_{ts}.json` directly inside it (available 2026-04-23)
- `ub25`: pass `${OUT}` as `$1` (script creates subdirectory inside it)
- `go`: `cd "${OUT}"` first, then call script with project dir as `$1`; JSON is written to CWD

If a requested product has no matching script: REPLAN via `/create-collect-script {product}` delegation (C3).

---

## Execution pattern (per product)

Each collection script MUST write its output into `collect/{QUAD}/{DATE}/collect/` (the `collect` subdirectory).
Each script has a different output interface — use the exact invocation below (verified 2026-04-23).

```bash
QUAD="{QUADRIGRAMME}"
DATE="{YYYYMMDD}"
PRODUCT="docker"      # adjust per product
OUT="${COLLECT_BASE}/${QUAD}/${DATE}/collect"

# Per-script invocation (verified against actual script interfaces)
case "${PRODUCT}" in
  docker)
    bash /opt/lia-sec/dev/scripts/collect/docker/Collect-Docker.sh "${OUT}/docker_config.json"
    ;;
  linux)
    # linux script accepts $1 as parent directory -- creates DATA_Linux_{ts}/ inside it (unified 2026-04-23)
    bash /opt/lia-sec/dev/scripts/collect/linux/collect_linux_all.sh "${OUT}"
    ;;
  postgres)
    bash /opt/lia-sec/dev/scripts/collect/postgresql/Collect-PostgreSQL.sh "${OUT}/postgresql_config.json"
    ;;
  k8s)
    bash /opt/lia-sec/dev/scripts/collect/kubernetes/Collect-Kubernetes.sh "${OUT}/k8s_config.json"
    ;;
  ub25)
    # ubuntu script accepts $1 as output directory -- it creates DATA_Ubuntu_CIS_{ts}/ inside it
    bash /opt/lia-sec/dev/scripts/collect/ubuntu/Collect-Ubuntu-v3.sh "${OUT}"
    ;;
  go)
    # go script writes go_{ts}.json to CWD; $1 = project dir to scan
    (cd "${OUT}" && bash /opt/lia-sec/dev/scripts/collect/go/collect_go.sh /opt/lia-sec/dev)
    ;;
  python)
    # python script accepts $1 as output directory -- writes python_{ts}.json inside it (available 2026-04-23)
    bash /opt/lia-sec/dev/scripts/collect/python/collect_python.sh "${OUT}"
    ;;
  *)
    echo "ERROR: unknown product '${PRODUCT}' -- delegate to /create-collect-script ${PRODUCT}"
    exit 2
    ;;
esac

# Verify non-empty output exists
NFILES=$(find "${OUT}" -type f 2>/dev/null | wc -l)
[ "${NFILES}" -gt 0 ] || { echo "COLLECTION EMPTY: no output files for ${PRODUCT} in ${OUT}"; exit 2; }
```

**Why absolute paths**: scripts are invoked from varying working directories; using absolute paths
ensures the script itself is found and that relative paths inside scripts resolve correctly.

---

## PostgreSQL tracking (per product start/done)

```bash
psql_lia() {
  PGPASSWORD="$LIA_DB_PASS" psql -h "$LIA_DB_HOST" -p "$LIA_DB_PORT" \
    -U "$LIA_DB_USER" -d "$LIA_DB_NAME" "$@"
}

# On collection start for a product
psql_lia -c "
  UPDATE grc_campaigns
  SET status = 'running', updated_at = NOW()
  WHERE id = '${GRC_CAMPAIGN_ID}';"

# On collection done for a product (N = products done so far, TOTAL = total products)
PROGRESS=$(echo "5 + 20 * ${N} / ${TOTAL}" | bc)
psql_lia -c "
  UPDATE grc_campaigns
  SET progress = ${PROGRESS}, updated_at = NOW()
  WHERE id = '${GRC_CAMPAIGN_ID}';"
```

---

## Verification queries after collection

```bash
# Files in collect/ subdirectory
ls -lh "${COLLECT_BASE}/${QUAD}/${DATE}/collect/"

# Confirm subdirectory tree is intact
find "${COLLECT_BASE}/${QUAD}/${DATE}" -type d | sort
```
