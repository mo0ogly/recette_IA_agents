# Reporting Phase -- Multi-format Export Loop

## Canonical call pattern

The backend `/api/export/professional` handler switches on `request.Format` and
produces **one artifact per call**. To deliver a complete audit package the
orchestrator MUST call the endpoint **once per target format** and enforce an
exit gate on all produced files.

Supported format values (handled by `professional_export_api.go`):

| format       | output extension | consumer use case                           |
|--------------|------------------|---------------------------------------------|
| `word`       | `.docx`          | Full written report for RSSI / auditor      |
| `excel`      | `.xlsx`          | Finding list + pivot tables for remediation |
| `powerpoint` | `.pptx`          | Executive slides for COMEX / steering com.  |
| `pdf`        | `.pdf`           | Optional signed deliverable (when enabled)  |

The orchestrator targets `word`, `excel`, `powerpoint` by default. `pdf` is
optional and only produced when the campaign context sets
`audit_context.include_pdf=true`.

## Bash template (MANDATORY)

Called from Phase 5 with these variables already defined:

- `CAMPAIGN_IDS` (bash array of `{QUAD}_{DATE}` strings)
- `QUADS` (bash array of quadrigrammes, primary first)
- `PRIMARY_QUAD` (first element of `QUADS`, used to locate the collect dir)
- `DATE` (YYYYMMDD)
- `SLUG` (session slug `co-YYYYMMDD-HHMMSS-...`)
- `LIA_API_TOKEN` (bearer from Phase 0)

```bash
EXPORT_DIR="/opt/lia-sec/dev/collect/${PRIMARY_QUAD}/${DATE}/exports"
mkdir -p "${EXPORT_DIR}"

# Basename uses _DATE once per quad, matching the backend default
# "LIA_{DATE}_{QUAD1}_{DATE}_{QUAD2}_{DATE}_..." pattern produced by the merge pipeline.
REPORT_BASENAME="LIA_${DATE}"
for Q in "${QUADS[@]}"; do
  REPORT_BASENAME="${REPORT_BASENAME}_${Q}_${DATE}"
done

declare -A EXPORT_EXT=( [word]=docx [excel]=xlsx [powerpoint]=pptx [pdf]=pdf )
TARGET_FORMATS=(word excel powerpoint)  # append "pdf" if include_pdf=true

FORMATS_DONE=0
for FMT in "${TARGET_FORMATS[@]}"; do
  EXT="${EXPORT_EXT[${FMT}]}"
  OUT="${EXPORT_DIR}/${REPORT_BASENAME}.${EXT}"

  PAYLOAD=$(jq -n \
    --argjson ids "$(printf '%s\n' "${CAMPAIGN_IDS[@]}" | jq -R . | jq -s .)" \
    --arg fmt "${FMT}" \
    --arg date "${DATE}" \
    --arg slug "${SLUG}" \
    --argjson quads "$(printf '%s\n' "${QUADS[@]}" | jq -R . | jq -s .)" \
    '{campaignIds:$ids, format:$fmt,
      options:{language:"en",reportLevel:"detailed"},
      auditContext:{quadrigrammes:$quads, date:$date, sessionSlug:$slug}}')

  HTTP=$(curl -s -o "${OUT}" -w "%{http_code}" \
    -X POST "http://localhost:8081/api/export/professional" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer ${LIA_API_TOKEN}" \
    -d "${PAYLOAD}")

  SIZE=$(stat -c%s "${OUT}" 2>/dev/null || echo 0)
  if [[ "${HTTP}" != "200" || "${SIZE}" -lt 1024 ]]; then
    log_orchestrator "ERROR" "REPORTING_FORMAT_FAILED" \
      "format=${FMT} http=${HTTP} size=${SIZE} out=${OUT}"
    continue
  fi

  log_orchestrator "INFO" "REPORTING_FORMAT_DONE" \
    "format=${FMT} size=${SIZE} out=${OUT}"
  FORMATS_DONE=$((FORMATS_DONE + 1))
done
```

## Exit gate (step 7 of Phase 5)

After the loop, every targeted format MUST exist non-empty on disk. A missing
format is an E4 exit; the cycle is FAILURE and cannot close.

```bash
for FMT in "${TARGET_FORMATS[@]}"; do
  EXT="${EXPORT_EXT[${FMT}]}"
  F="${EXPORT_DIR}/${REPORT_BASENAME}.${EXT}"
  if [[ ! -s "${F}" ]]; then
    log_orchestrator "ERROR" "REPORTING_EXIT_GATE_FAILED" \
      "missing_format=${FMT} path=${F}"
    exit 4
  fi
done
log_orchestrator "INFO" "REPORTING_EXIT_GATE_PASS" \
  "formats=${FORMATS_DONE}/${#TARGET_FORMATS[@]} dir=${EXPORT_DIR}"
```

## Why a loop instead of one multi-format call

`handleProfessionalExport` in `cmd/sigma_web/professional_export_api.go` is a
single `switch request.Format` with one generator per case
(`generateProfessionalWord`, `generateProfessionalExcel`,
`generateProfessionalPowerPoint`, `generateProfessionalPDF`). There is no
multi-format endpoint and no array syntax. The skill contract of "Word +
Excel + PowerPoint" maps to 3 HTTP calls.

## professional_exports DB row side effect

Each call inserts one row in `professional_exports`. The backend sets
`file_path` to `_alire/temp/exports/LIA_{TODAY}_{QUADS}.{ext}` using the
current server date, NOT the campaign date. This is a backend-side naming
quirk (tracked as bug M5 in the cycle 4 RETEX). The skill does not rely on
`professional_exports.file_path` — the canonical artifact for UX delivery is
the one written under `collect/{PRIMARY_QUAD}/{DATE}/exports/` (step 3 of
Phase 5). Both paths exist on disk after Phase 5.

## Failure modes and REPLAN alternatives

| Failure                        | REPLAN alt1                           | REPLAN alt2                                 |
|--------------------------------|---------------------------------------|---------------------------------------------|
| `word` returns HTTP 500        | retry the same call once              | log MERGE_DATA_INSUFFICIENT, skip word, fail exit gate |
| `excel` returns size < 1 KB    | retry with `reportLevel: "summary"`   | skip excel, fail exit gate                  |
| `powerpoint` returns HTTP 500  | retry the same call once              | invoke `/pptx-recette` to diagnose template |
| `pdf` unsupported / disabled   | skip silently (optional format)       | N/A                                         |

A cycle that only produces 1 or 2 of the 3 mandatory formats is INCOMPLETE
(the exit gate blocks). REPLAN adds the missing format(s) on retry.
