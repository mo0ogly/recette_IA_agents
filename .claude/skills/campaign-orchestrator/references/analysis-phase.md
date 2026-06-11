# Analysis Phase -- Backend API, Path Resolution, and Engine Execution

## Source of truth

- Handler: `cmd/sigma_web/analysis_handlers_api.go` (line 134+)
- Engine: `cmd/sigma_web/analysis_engine_real.go` `ExecuteRealAnalysis()` (line 52+)
- Endpoint: `POST /api/analysis/execute`

---

## API payload (verified from analysis_handlers_api.go line 134-135)

```json
{
  "collection_id": "ADDS",
  "taxonomy_id":   "Active Directory"
}
```

| Field | Type | Role | Notes |
|-------|------|------|-------|
| `collection_id` | string | QUAD used as key to locate data on disk | Maps to `collect/{collection_id}/` on disk. Can also be an absolute path to a directory or file. |
| `taxonomy_id` | string | Taxonomy branch applied | e.g. `"Active Directory"`, `"Docker"`, `"PostgreSQL"` |
| `quadrigramme` | string (optional) | Explicit QUAD override | If absent the engine derives it from `collection_id` |

**The old payload format (`quadrigramme`, `date`, `rulesDir`, `eventsDir`, `mode`, `matchingMode`) is NOT accepted by this endpoint.** Those were engine CLI flags, not HTTP fields.

---

## Path resolution inside ExecuteRealAnalysis()

```
collection_id = "ADDS"
  -> absolute path? use as-is (file -> parent dir, directory -> as-is)
  -> relative?      search ../../collect/ADDS first, then ../../results/ADDS
```

Given the binary runs from `cmd/sigma_web/`, `../../collect/{collectionID}` resolves to:
```
/opt/lia-sec/dev/collect/{QUAD}/{DATE}    # when date is embedded in the path
/opt/lia-sec/dev/collect/{QUAD}           # when passed as bare QUAD
```

**Best practice**: pass the absolute path to the campaign's `collect/` subdirectory as `collection_id`:
```bash
collection_id = "${COLLECT_BASE}/${QUAD}/${DATE}/collect"
```
This guarantees the engine finds the files regardless of cwd.

---

## Output files

| File | Path | Written by |
|------|------|-----------|
| Analysis results JSON | `_alire/temp/analysis_{resultID}.json` | `ExecuteRealAnalysis()` |
| Analysis log | `_alire/temp/analysis_{resultID}.log` | `ExecuteRealAnalysis()` |
| `analysis_results.json` (via handler) | `collect/{QUAD}/{DATE}/analyse/results/analysis_results.json` | `createAnalysisDirectory()` in handler |

The in-memory result is also stored in `preparationResults[analysisID]` for polling.

---

## Invocation from the orchestrator

```bash
QUAD="{QUADRIGRAMME}"
DATE="{YYYYMMDD}"
TAXONOMY="{TAXONOMY_ID}"       # e.g. "Active Directory", "Docker", "PostgreSQL"
COLLECT_BASE="${COLLECT_BASE:-/opt/lia-sec/dev/collect}"

# Use absolute path to the collect subdirectory so the engine cannot miss it
COLLECTION_PATH="${COLLECT_BASE}/${QUAD}/${DATE}/collect"

ANALYSIS_RESP=$(curl -s -X POST \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${LIA_API_TOKEN}" \
  -d "{\"collection_id\":\"${COLLECTION_PATH}\",\"taxonomy_id\":\"${TAXONOMY}\",\"quadrigramme\":\"${QUAD}\"}" \
  http://localhost:8081/api/analysis/execute)

# Unwrap envelope (R17: backend returns {success, data})
ANALYSIS_ID=$(echo "${ANALYSIS_RESP}" | jq -r '.data.id // .id')
STATUS=$(echo "${ANALYSIS_RESP}" | jq -r '.data.status // .status')

[ -n "${ANALYSIS_ID}" ] && [ "${ANALYSIS_ID}" != "null" ] || {
  echo "ERROR: analysis/execute failed: ${ANALYSIS_RESP}"
  exit 2
}
```

---

## Polling the status

```bash
while true; do
  POLL=$(curl -s \
    -H "Authorization: Bearer ${LIA_API_TOKEN}" \
    "http://localhost:8081/api/analysis/${ANALYSIS_ID}")
  STATUS=$(echo "${POLL}" | jq -r '.data.status // .status')
  PROGRESS=$(echo "${POLL}" | jq -r '.data.progress // 0')

  case "${STATUS}" in
    completed) break ;;
    error|failed)
      ERROR=$(echo "${POLL}" | jq -r '.data.variables.error // "unknown"')
      echo "ANALYSIS FAILED: ${ERROR}"
      exit 1 ;;
    running|*)
      # Scale to orchestrator progress band 25-65%
      SCALED=$(echo "25 + 40 * ${PROGRESS} / 100" | bc 2>/dev/null || echo 40)
      psql_lia -c "UPDATE grc_campaigns SET progress = ${SCALED}, updated_at = NOW() WHERE id = '${GRC_CAMPAIGN_ID}';"
      sleep 2 ;;
  esac
done

# Read result
RESULT_FINDINGS=$(curl -s \
  -H "Authorization: Bearer ${LIA_API_TOKEN}" \
  "http://localhost:8081/api/analysis/results/${ANALYSIS_ID}" \
  | jq '.data.statistics.total_findings // 0')
```

---

## Taxonomy ID mapping per product

The `taxonomy_id` value must match what `loadAuditRules(taxonomyID)` expects.
Verify in `config/taxonomy/{QUAD}_taxonomy.json` if a custom mapping exists.
Default safe values:

| Product | taxonomy_id |
|---------|------------|
| `docker` | `"Docker"` or `"ContainerRuntime"` |
| `linux` | `"Linux"` or `"Hardening"` |
| `postgres` | `"PostgreSQL"` |
| `k8s` | `"Kubernetes"` |
| AD-based quads (ADDS, etc.) | `"Active Directory"` |

If `loadAuditRules(taxonomyID)` returns 0 rules: the analysis completes with 0 findings
(no error). REPLAN: check `config/taxonomy/` for the correct taxonomy name.

---

## Direct CLI fallback (REPLAN alt)

If `POST /api/analysis/execute` returns 5xx, use the engine directly:

```bash
./bin/lia_scan_engine \
  -multi \
  -rules lia_rules/ \
  -events "${COLLECT_BASE}/${QUAD}/${DATE}/collect" \
  -quadrigramme "${QUAD}" \
  -date "${DATE}" \
  -json "_alire/temp/campaign-orchestrator/${SLUG}/analysis/${QUAD}.json"
```

Add `-scan-multirules` when the `-R` flag is set on the orchestrator.

---

## Logging

```
LogSystemEvent("INFO", "CAMPAIGN_ORCHESTRATOR", "ANALYSIS_START",
  "slug={slug} quad={quad} collection_path={path} taxonomy={tx}")

LogSystemEvent("INFO", "CAMPAIGN_ORCHESTRATOR", "ANALYSIS_DONE",
  "slug={slug} quad={quad} analysis_id={id} findings={n}")
```
