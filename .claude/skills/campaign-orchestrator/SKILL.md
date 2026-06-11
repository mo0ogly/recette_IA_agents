---
name: campaign-orchestrator
description: "Orchestrate an end-to-end LIA-SEC audit campaign across multiple products (Docker, Linux, PostgreSQL, Kubernetes) on the VPS. Autonomous OODA loop v5.0 cycle INIT -> OBSERVE -> COLLECTION -> ANALYSIS -> MERGE -> REPORTING -> RECETTE -> COMPLETE. Every phase inserts its status into PostgreSQL (grc_campaigns, batch_wave_runs, unified_logs) AND is visible in the UX (CampaignManager, CampaignCalendar, LogManager). The -R flag maps to lia_scan_engine -scan-multirules + MergeRequest.IncludeRuleReports=true. Composes with /create-collect-script (missing scripts), /recette-lia-rule (rule validation), /apex (v2 code generation), /konrad-kurze (meta-cognitive auditor on stalled REPLAN loops). Triggers on /campaign-orchestrator, 'lance une campagne', 'orchestre campagne', 'workflow campagne', 'campagne multi-produits', 'run end-to-end audit campaign', 'docker linux postgres kubernetes campaign'."
---

# Campaign Orchestrator v1.0 -- Autonomous End-to-End Audit Campaign

Autonomous level-5 agentic loop that reproduces the full LIA-SEC campaign workflow on the VPS with multiple products. Every phase is persisted in PostgreSQL AND surfaced in the UX in real time.

Companion file: [SKILL_REFERENCE.md](SKILL_REFERENCE.md) -- taxonomy table, QUAD registration, verification queries, out-of-scope list.

## Path conventions (W0.2 -- client level in /collect/)

Collect base is resolved through `system_variables.COLLECT_PATH` (R5
PostgreSQL first). Two layouts coexist; the resolver
(`cmd/sigma_web/collect_path_resolver.go`) tries the NEW layout first and
falls back transparently to the LEGACY layout. Existing directories are
never moved.

1. NEW layout (preferred for any new campaign):

   ```
   <COLLECT_BASE>/<CLIENT_QUADRIGRAMME>/<TECHNO>/<YYYYMMDD>/
   ```

   `CLIENT_QUADRIGRAMME` = `^[A-Z0-9_]{2,16}$` (ex: `ACME`, `BANK01`).
   `TECHNO` = short technology code, `^[A-Z0-9_]{1,32}$` (ex: `ADDS`,
   `DOCK`, `GO`, `POSTGRESQL`, `REACT`, `UB25`). This is the value
   historically referenced as `<QUAD>` in legacy docs; the REAL client
   quadrigramme now lives one level above.

2. LEGACY layout (still supported read/write):

   ```
   <COLLECT_BASE>/<TECHNO>/<YYYYMMDD>/
   ```

Resolution order: `ResolveCampaignPath(client, techno, date)` tries
`<base>/<client>/<techno>/<date>/` then `<base>/<techno>/<date>/`.
Creation: `EnsureCampaignDirectory(client, techno, date)` uses the new
layout when `client != ""`, otherwise legacy. Orchestrator phases MUST
call these helpers (or their SQL equivalents via the `ad_display_campaigns`
row which now carries `client_quadrigramme`) and MUST NOT concatenate
paths manually. Any top-level directory that does not match the regex is
logged as `SECURITY WARN` and skipped during the disk scan.

## Tracing helper (MANDATORY)

Define this helper ONCE at session start, BEFORE Phase 0 pre-flight. Every phase MUST call
`log_orchestrator` at least once so the run is auditable in `unified_logs` (UX Log Manager).
Retex 2026-04-24 proved a skill without executable logging appears to work but leaves zero
trace for the user -- this helper fixes the gap.

```bash
# Pre-requisite: psql_lia() already defined (see "Pre-requisites" section below).
# If not, the helper self-tests and aborts -- no silent failure.

log_orchestrator() {
    local LEVEL="${1:?LEVEL required (INFO|WARN|ERROR|DEBUG)}"
    local ACTION="${2:?ACTION required (INIT_DONE, COLLECTION_DONE, ...)}"
    local MSG="${3:-}"
    type psql_lia &>/dev/null || { echo "ERROR: log_orchestrator requires psql_lia()" >&2; return 1; }
    # $$...$$ dollar-quoting avoids shell-escaping issues with slugs/paths containing quotes.
    psql_lia -tAc "INSERT INTO unified_logs (timestamp, level, component, action, message) VALUES (NOW(), \$\$${LEVEL}\$\$, 'CAMPAIGN_ORCHESTRATOR', \$\$${ACTION}\$\$, \$\$${MSG}\$\$);" >/dev/null
}
```

Minimum call count per 5-QUAD run : **23 events** (1 INIT_DONE + 2 OBSERVE + 5 COLLECTION_DONE
+ 5 ANALYSIS_DONE + 5 COMPLIANCE_DONE + 1 MERGE_DONE + 2 REPORTING + 1 RECETTE_PASS + 1 CAMPAIGN_COMPLETE).
A COMPLIANCE_DONE event may be replaced by a COMPLIANCE_SKIPPED (missing execution_stats.json)
or COMPLIANCE_FAILED (engine error) entry per QUAD ; presence of one of those three actions
per QUAD is required. Verify at end of Phase 7 with:

```bash
psql_lia -tAc "SELECT COUNT(*) FROM unified_logs WHERE component = 'CAMPAIGN_ORCHESTRATOR' AND message LIKE '%${SLUG}%' AND timestamp >= NOW() - INTERVAL '24 hours';"
```

If `< 23`, Phase 7 gate fails -- a missing call means an untraced phase, operator must diagnose.

## Core: the loop (autonomous agent pattern)

```text
OBJECTIVE
   |
   v
DECOMPOSE  (3-7 subtasks, dependencies, complexity per subtask: TRIVIAL|MODERATE|COMPLEX)
   |
   v
PLAN       (for each subtask: goal, tool, expected output, success criteria, failure signal)
   |
   v
ACT        (one tool at a time unless calls are independent; capture full result)
   |
   v
OBSERVE    (state what happened factually; compare actual vs expected)
   |
   v
EVALUATE   (classify: SUCCESS | PARTIAL | FAILURE, then DECIDE)
   |
   +-- SUCCESS  -> log + move to next subtask
   +-- PARTIAL  -> retry with adjustment or accept and continue
   +-- FAILURE  -> REPLAN (diagnose, 2+ alternatives, select best, never same action)
                   |
                   +-- 3 consecutive REPLAN on same subtask -> ESCALATE to user
   |
   v
LOOP or COMPLETE
```

Mapped onto the campaign workflow:

```text
INIT (DECOMPOSE+PLAN+pre-flight) -> OBSERVE (inventory + grc_campaigns row)
  -> COLLECTION (parallel: docker, linux, postgres, k8s)  [ACT+OBSERVE+EVALUATE per product]
  -> ANALYSIS  (lia_scan_engine via /api/analysis/execute  +  lia_compliance_engine CLI per QUAD)
  -> MERGE     (/api/reports/merge with includeRuleReports = -R)
  -> REPORTING (/api/export/professional Word + Excel + PowerPoint, loop)
  -> RECETTE   (/recette-lia-rule + Playwright smoke on CampaignManager)
  -> COMPLETE  (RETEX displayed with per-subtask SUCCESS|PARTIAL|FAILURE + Librarian Gate)
```

Note: Phase ANALYSIS now includes an automatic compliance-engine pass per QUAD so that Phase REPORTING can render Section 4b "Compliance Engine Report" in Word without manual invocation. See Phase 3 step 6 below.

The agent loops until the campaign reaches `completed` in `grc_campaigns` with a valid PPTX report, or escalates after 3 REPLAN failures on the same subtask.

---

## Syntax

```
/campaign-orchestrator <QUAD[,QUAD...]> [options]
```

| Flag | Description | Default |
|------|-------------|---------|
| `--products <list>` | Comma-separated product list: `docker,linux,postgres,k8s` | all four |
| `--date <YYYYMMDD>` | Campaign date | today (UTC) |
| `-R` / `--include-rule-reports` | Enable `scan-multirules` + `MergeRequest.IncludeRuleReports=true` | off |
| `--ai` | Enable AI-enhanced merge insights (`enableAI: true`) | off |
| `--dry-run` | Print the plan, INSERT draft `grc_campaigns` row, do NOT run scripts or engine | off |
| `-r <session-slug>` | Resume from an existing session slug | - |

**Default: AUTONOMOUS.** No confirmation between phases. Escalates only when autonomy perimeter is exceeded (see `_shared/references/agentic-core.md` section 2).

### --dry-run walkthrough

When `--dry-run` is set the agent prints the execution plan and creates a draft `grc_campaigns` row, but does NOT run any collection script, analysis engine call, merge, or export.

Expected output (example: `/campaign-orchestrator ADDS --products docker,linux --dry-run`):

```text
[DRY-RUN] Session slug : co-20260422-143000-adds
[DRY-RUN] Products     : docker, linux
[DRY-RUN] Date         : 20260422
[DRY-RUN] COLLECT_BASE : /opt/lia-sec/dev/collect  (from system_variables.COLLECT_PATH)
[DRY-RUN] Phase 0 INIT
  - Would create: _alire/temp/campaign-orchestrator/co-20260422-143000-adds/
  - Would create: _alire/tracking/PLAN_CAMPAIGN_ORCHESTRATOR_co-20260422-143000-adds_2026-04-22.md
  - Would INSERT grc_campaigns (name="Orchestrated campaign co-20260422-143000-adds", status=draft)
  - grc_campaign_id: <would be set after INSERT>
[DRY-RUN] Phase 1 OBSERVE
  - Would verify collect/ADDS/20260422/ directory tree
  - Would UPDATE grc_campaigns.metadata with session JSONB
[DRY-RUN] Phase 2 COLLECTION (2 products in parallel)
  - Would run: scripts/collect/docker/Collect-Docker.sh collect/ADDS/20260422/collect/docker_config.json
  - Would run: scripts/collect/linux/collect_linux_all.sh  (tmpdir + mv DATA_Linux_*/ -> collect/ADDS/20260422/collect/)
[DRY-RUN] Phase 3 ANALYSIS
  - Would POST /api/analysis/execute with taxonomy_id="ADDS" quadrigramme="ADDS"
[DRY-RUN] Phase 4 MERGE
  - Would POST /api/reports/merge with campaignIds=["ADDS/20260422"] includeRuleReports=false
[DRY-RUN] Phase 5 REPORTING
  - Would POST /api/export/professional 3x (word, excel, powerpoint)
[DRY-RUN] Phase 6 RECETTE
  - Would invoke /recette-lia-rule + Playwright smoke
[DRY-RUN] All checks passed. Remove --dry-run to execute.
```

Use `--dry-run` to verify prerequisites (scripts present, backend healthy, taxonomy resolvable) before committing CPU time to a full run.

### Multi-quad invocation example

When running the same DATE across N quadrigrammes (e.g. quarterly scan of the full client estate):

```bash
QUADS="ADDS EXCH DOCK LNXS"
DATE="20260422"

for QUAD in ${QUADS}; do
  echo "--- Launching ${QUAD}/${DATE} ---"
  curl -s -X POST -H "Authorization: Bearer ${LIA_API_TOKEN}" -H "Content-Type: application/json" -d "{\"name\":\"Orchestrated campaign ${QUAD}-${DATE}\",\"quadrigramme\":\"${QUAD}\",\"date\":\"${DATE}\"}" http://localhost:8081/api/campaigns/create-structure
done
```

Key rules for multi-quad runs:
- Each QUAD generates its own `grc_campaigns` row and its own `campaign_workflow_runs` set.
- Progress is tracked per-QUAD independently; the orchestrator loops over `QUADS` sequentially (parallel only when resources allow and scripts do not share output directories).
- Merge (Phase 4) consolidates ALL QUADs sharing the same DATE: `"campaignIds": ["ADDS/20260422","EXCH/20260422","DOCK/20260422","LNXS/20260422"]`.
- If a QUAD fails collection, the others continue; the failed QUAD is retried independently (REPLAN scope = single QUAD, not the whole run).
- DATE collision per QUAD is detected via `jq -e '.success == false'` on the `create-structure` call (see edge case matrix above); use `-r <existing-slug>` to resume.

### Progress bands

| Band | Range | Phase |
|------|-------|-------|
| Init | 0% | Phase 0/1 (row created, not started) |
| Collection start | 5% | Phase 2 first product PUT status=running |
| Collection | 5-25% | `5 + 20 * (done_products / total_products)` |
| Analysis | 25-65% | `25 + 40 * (analysis_pct / 100)` polled from engine |
| Merge | 65-75% | Set to 75 on merge success (Phase 4) |
| Reporting | 75-100% | Set to 100 when all 3 formats (word+excel+powerpoint) pass the exit gate (Phase 5 step 7) |
| Complete | 100% | `grc_campaigns.status = completed` |

Max REPLAN count: **3 consecutive failures on the same subtask** -> ESCALATE to user (no further autonomous retry).

**Konrad-Kurze meta-cognitive gate (BEFORE the 3rd REPLAN).** When a subtask
hits its 2nd REPLAN in the same session AND no APPROVED KD already addresses
this subtask:

1. INVOKE `/konrad-kurze` via the Skill tool (model: **sonnet**) with scope =
   `campaign-orchestrator/{slug}/{phase}/{subtask}`. Pass the
   `decision_log.jsonl` for this session and the relevant `unified_logs`
   slice as evidence.
2. Read the emitted directive at
   `_alire/02_LOGS/Journals/meta/directives/KD-{id}.json`.
3. If `risk_level = LOW` AND `injection.operation = ADD` AND
   `requires_approval = false`: apply the directive as the 3rd REPLAN
   alternative (e.g. an ADDITIONAL probe, log line, or pre-check). Log
   `action="KONRAD_DIRECTIVE_APPLIED"` in `decision_log.jsonl`.
4. Else (MEDIUM / HIGH or `requires_approval = true`): surface the
   directive to the user as part of the ESCALATE message. Do NOT
   auto-apply.

This gate inserts a meta-diagnosis BEFORE the rigid escalation, so the
user receives a classified failure (CONVENTION_CONFLICT, GHOST_REDUNDANCY,
META_DATA_AMNESIA, PHYSICAL_VISUAL_MISMATCH, LEMANRUSS_TAINT) and a bounded
recommendation rather than just "we tried 3 times". See
`.claude/skills/konrad-kurze/SKILL.md` for the directive schema.

### Edge case matrix

| Scenario | Detection | REPLAN alt1 | REPLAN alt2 |
|----------|-----------|-------------|-------------|
| Empty collection output (`collect/{QUAD}/{DATE}/collect/` is empty or missing) | `find ... -type f | wc -l` returns 0 after script completes | Re-run script with `--verbose` flag to diagnose; check disk space and permissions | Delegate `/create-collect-script {product}` to generate a corrected script |
| Analysis engine 5xx (`/api/analysis/execute` returns HTTP 5xx) | `ANALYSIS_ID` null or `jq -r '.error'` non-null | Retry once after 30s with identical payload | Fall back to direct CLI: `bin/lia_scan_engine -multi -rules . -events ...` |
| Merge failure (`/api/reports/merge` 5xx with `enableAI=true`) | HTTP 5xx on merge call | Retry with `enableAI=false` | Inspect `unified_logs WHERE component LIKE 'MERGE%'` for root cause, fix and retry |
| Network timeout (curl command exits non-zero or returns empty body) | `curl` exit code != 0 or body is `""` | Retry with `--retry 3 --retry-delay 5` appended to curl | Switch to direct `psql_lia` SQL path if the API call has a SQL equivalent |
| Duplicate QUAD + DATE (campaign already exists for this QUAD/DATE combination) | `jq -e '.success == false'` on `POST /api/campaigns/create-structure` | Resume with `-r <existing-slug>` if the slug is known | Use `--date` with a different DATE suffix (append `-v2`) to create a fresh campaign |
| Script non-zero exit (collection script fails mid-run) | Script `$?` != 0 in Phase 2 loop | Re-run script in isolation with `bash -x` to capture error line | Check for missing binary dependencies (`which jq`, `which xmllint`) and install |
| PostgreSQL connection refused (`psql_lia` exits non-zero) | `psql_lia -c "SELECT 1"` fails | Run `./cleanup_services.sh status` and restart PostgreSQL if needed | Wait 30s and retry; escalate if still failing after 3 attempts |

---

## Shared references

Read BEFORE executing:

| Reference | Content |
|-----------|---------|
| [_shared/references/agentic-core.md](../_shared/references/agentic-core.md) | 3-level memory, autonomy perimeter, model selection, pre-flight, /50 score |
| [_shared/references/librarian-gate.md](../_shared/references/librarian-gate.md) | End-of-cycle blocking checklist |
| [_shared/references/retex-protocol.md](../_shared/references/retex-protocol.md) | RETEX template and scoring |
| [references/collection-phase.md](references/collection-phase.md) | Product -> script mapping, output layout `collect/{QUAD}/{DATE}/collect/` (no product subdirectory) |
| [references/analysis-phase.md](references/analysis-phase.md) | `lia_scan_engine` flags, `/api/analysis/execute`, polling protocol |
| [references/merge-phase.md](references/merge-phase.md) | `MergeRequest` payload, `-R` semantics, error handling |
| [references/reporting-phase.md](references/reporting-phase.md) | `/api/export/professional` multi-format loop (word + excel + powerpoint) + exit gate |
| [references/postgres-tracking.md](references/postgres-tracking.md) | Tables, INSERT/UPDATE patterns, v2 migration 101 |
| [references/ux-visibility.md](references/ux-visibility.md) | UX endpoints, deeplinks, optional v2 dashboard |

---

## Phase 0 : INIT (pre-flight + resume)

1. **Parse arguments**: quadrigrammes (required), `--products` list, `--date`, flags.
2. **Resume check** (`-r <slug>`): if slug exists in `_alire/temp/campaign-orchestrator/{slug}/FILE_TRACKER.json`, load and continue from `recovery.next_step`. Else fresh.
3. **Generate session slug**: `co-{YYYYMMDD-HHMMSS}-{quad-slug}`.
4. **Create PLAN immediately**: copy `templates/PLAN_CAMPAIGN_ORCHESTRATOR.md.tmpl` to `_alire/tracking/PLAN_CAMPAIGN_ORCHESTRATOR_{slug}_{YYYY-MM-DD}.md`. Fill header (invocation, session slug, products, date).
5. **Pre-flight** (BLOCKING):
   ```bash
   test -x /opt/lia-sec/dev/bin/lia_scan_engine || ./cmd/sigma_web/build_secure_lia.sh
   curl -s -o /dev/null -w "%{http_code}" http://localhost:8081/api/health
   PGPASSWORD="$LIA_DB_PASS" psql -h localhost -U lia_admin -d lia_scan -c "SELECT 1" >/dev/null
   ```
   If any fails: STOP, ESCALATE. Exception for backend down: run `./cleanup_services.sh both` once before aborting.
6. **Script presence check** (per product requested):
   - `docker` -> `scripts/collect/docker/Collect-Docker.sh`
   - `linux` -> `scripts/collect/linux/collect_linux_all.sh`
   - `postgres` -> `scripts/collect/postgresql/Collect-PostgreSQL.sh`
   - `k8s` -> `scripts/collect/kubernetes/Collect-Kubernetes.sh`

   Any missing -> REPLAN with `/create-collect-script {product}` delegation (C3).
7. **Resolve COLLECT_BASE** (path where all campaigns are stored):
   ```bash
   COLLECT_BASE=$(psql_lia -tAc "SELECT value FROM system_variables WHERE key = 'COLLECT_PATH' LIMIT 1")
   COLLECT_BASE="${COLLECT_BASE:-/opt/lia-sec/dev/collect}"
   ```
   Store in `FILE_TRACKER.json` under `session.collect_base`.
8. **Create campaign directory structure** via API (BLOCKING, per quadrigramme):
   ```bash
   # For each QUAD in the quadrigrammes list:
   curl -s -X POST -H "Content-Type: application/json" -H "Authorization: Bearer ${LIA_API_TOKEN}" -d "{\"quadrigramme\":\"${QUAD}\",\"date\":\"${DATE}\"}" http://localhost:8081/api/campaigns/create-structure | jq -e '.success == true'
   ```
   This creates `collect/{QUAD}/{DATE}/` with subdirs `collect/`, `prepare/`, `analyse/{stats,results,logs,rules_results}`, `report/`, `display/`, `compliance/`. See [references/collection-phase.md](references/collection-phase.md) for the full tree.
   If the call fails: STOP, ESCALATE (directory creation is prerequisite for all subsequent phases).
9. **Initialize session artifacts** in `_alire/temp/campaign-orchestrator/{slug}/`:
   - `action_journal.jsonl`, `FILE_TRACKER.json`, `decision_log.jsonl` (empty).
   - Create subdirs: `analysis/`, `merge/`, `reports/`.
10. **Log INIT complete** (executable):
    ```bash
    log_orchestrator "INFO" "INIT_DONE" "slug=${SLUG} products=${PRODUCTS} quads=${QUADS} date=${DATE}"
    ```

---

## Phase 1 : OBSERVE (inventory + grc_campaigns row)

1. Build product -> script map; resolve quadrigramme -> taxonomy via `config/taxonomy/{QUAD}_taxonomy.json`.
2. Confirm the directory tree is in place (created in Phase 0). Expected structure per quadrigramme:
   ```
   collect/{QUAD}/{DATE}/
   ├── collect/              # XMLs / JSONs from collection scripts (written in Phase 2)
   ├── prepare/              # Pre-processed data
   ├── analyse/
   │   ├── stats/
   │   ├── results/          # analysis_results.json written here by engine
   │   ├── logs/
   │   └── rules_results/
   ├── report/               # Final PPTX / DOCX
   ├── display/              # UI display data
   └── compliance/           # Compliance outputs
   ```
   Verify with `find "${COLLECT_BASE}/${QUAD}/${DATE}" -type d | sort`. If missing: re-run Phase 0 step 8.
3. **CREATE campaign via API** (same path as frontend — triggers `RecordAuditEvent` + `LogSystemEvent`):
   ```bash
   CREATE_RESP=$(curl -s -X POST -H "Content-Type: application/json" -H "Authorization: Bearer ${LIA_API_TOKEN}" -d "{\"name\":\"Orchestrated campaign ${SLUG}\",\"description\":\"Products: ${PRODUCTS} | Quads: ${QUADS} | -R: ${R_FLAG} | AI: ${AI_FLAG}\",\"client_id\":\"${QUAD}\",\"start_date\":\"${CAMPAIGN_DATE}\"}" http://localhost:8081/api/grc/campaigns)
   GRC_CAMPAIGN_ID=$(echo "${CREATE_RESP}" | jq -r '.id // empty')
   [ -n "${GRC_CAMPAIGN_ID}" ] || { echo "ERROR: grc_campaigns create failed: ${CREATE_RESP}"; exit 2; }
   ```
   Then inject the session metadata (not supported by the create endpoint) via direct SQL — only for the `metadata` JSONB field (not covered by the API):
   ```bash
   PRODUCTS_SQL=$(echo "${PRODUCTS}" | sed "s/\([^,]*\)/'\1'/g")
   QUADS_SQL=$(echo "${QUADS}" | sed "s/\([^,]*\)/'\1'/g")
   psql_lia -c "UPDATE grc_campaigns SET metadata = jsonb_build_object('session_slug','${SLUG}','products',ARRAY[${PRODUCTS_SQL}],'quadrigrammes',ARRAY[${QUADS_SQL}],'include_rule_reports',${R_FLAG},'enable_ai',${AI_FLAG},'collect_base','${COLLECT_BASE}','source_skill','campaign-orchestrator','skill_version','1.0') WHERE id = '${GRC_CAMPAIGN_ID}';"
   ```
   Store `GRC_CAMPAIGN_ID` in `FILE_TRACKER.json` under `session.metadata.grc_campaign_id`.
   NOTE: `progress` updates throughout the pipeline use direct SQL (`UPDATE grc_campaigns SET progress = N WHERE id = '...'`) because the `PUT /api/grc/campaigns/{id}` endpoint does not expose the `progress` column.
4. If migration 101 applied (table `campaign_workflow_runs` exists): INSERT one row per (phase, product) with status `pending`.
5. **Log OBSERVE complete** (executable, 2 events) :
   ```bash
   log_orchestrator "INFO" "OBSERVE_DONE" "slug=${SLUG} quads_inventoried=${#QUADS_ARRAY[@]}"
   log_orchestrator "INFO" "CAMPAIGN_REGISTERED" "grc_campaign_id=${GRC_CAMPAIGN_ID} slug=${SLUG}"
   ```
6. On API CREATE failure: REPLAN (alt1: retry once after 3s with identical payload; alt2: INSERT directly via `psql_lia` and store ID manually — only if backend consistently unreachable).

---

## Phase 2 : COLLECTION (parallel per product)

All collection scripts write their output into `collect/{QUAD}/{DATE}/collect/` (the `collect` subdirectory, NOT the campaign root). See [references/collection-phase.md](references/collection-phase.md).

For each product, in parallel:

1. On first product: call `PUT /api/grc/campaigns/${GRC_CAMPAIGN_ID}` with `{"status":"running"}` (status is in `allowedCols`). Progress updates remain direct SQL (not exposed by the PUT handler):
   ```bash
   STATUS_RESP=$(curl -s -X PUT -H "Content-Type: application/json" -H "Authorization: Bearer ${LIA_API_TOKEN}" -d "{\"status\":\"running\"}" "http://localhost:8081/api/grc/campaigns/${GRC_CAMPAIGN_ID}")
   echo "${STATUS_RESP}" | jq -e '.success == true' > /dev/null || echo "WARN: status update non-success: ${STATUS_RESP}"
   psql_lia -c "UPDATE grc_campaigns SET progress = 5, updated_at = NOW() WHERE id = '${GRC_CAMPAIGN_ID}';"
   ```
2. If `campaign_workflow_runs` exists: UPDATE row `(phase='collection', product=X)` -> `running`, set `started_at`.
3. Execute script using the per-script interface (verified against actual scripts -- no script accepts `--output`):
   ```bash
   OUT="${COLLECT_BASE}/${QUAD}/${DATE}/collect"
   case "${PRODUCT}" in
     docker)
       bash /opt/lia-sec/dev/scripts/collect/docker/Collect-Docker.sh "${OUT}/docker_config.json"
       ;;
     linux)
       LXTMP=$(mktemp -d /opt/lia-sec/dev/_alire/temp/linux_collect_XXXXXX)
       (cd "${LXTMP}" && bash /opt/lia-sec/dev/scripts/collect/linux/collect_linux_all.sh)
       mv "${LXTMP}"/DATA_Linux_*/ "${OUT}/"
       rm -rf "${LXTMP}"
       ;;
     postgres)
       bash /opt/lia-sec/dev/scripts/collect/postgresql/Collect-PostgreSQL.sh "${OUT}/postgresql_config.json"
       ;;
     k8s)
       bash /opt/lia-sec/dev/scripts/collect/kubernetes/Collect-Kubernetes.sh "${OUT}/k8s_config.json"
       ;;
     ub25)
       bash /opt/lia-sec/dev/scripts/collect/ubuntu/Collect-Ubuntu-v3.sh "${OUT}"
       ;;
     go)
       (cd "${OUT}" && bash /opt/lia-sec/dev/scripts/collect/go/collect_go.sh /opt/lia-sec/dev)
       ;;
     python)
       echo "ERROR: no collect script for python -- delegate to /create-collect-script python"
       exit 2
       ;;
     *)
       echo "ERROR: unknown product '${PRODUCT}' -- delegate to /create-collect-script ${PRODUCT}"
       exit 2
       ;;
   esac
   ```
   See [references/collection-phase.md](references/collection-phase.md) for the full interface notes per script.
4. Verify non-empty output in `collect/{QUAD}/{DATE}/collect/`:
   ```bash
   NFILES=$(find "${OUT}" -type f 2>/dev/null | wc -l)
   [ "${NFILES}" -gt 0 ] || { echo "COLLECTION EMPTY for ${PRODUCT}"; exit 2; }
   ```
5. UPDATE `campaign_workflow_runs` -> `succeeded` with metadata (file count, sizes).
6. **Log COLLECTION_DONE** (executable, 1 per product/quad pair):
   ```bash
   log_orchestrator "INFO" "COLLECTION_DONE" "product=${PRODUCT} quad=${QUAD} files=${NFILES}"
   ```
7. On failure: REPLAN (alt1: rerun with `--verbose`, alt2: regenerate via `/create-collect-script`). Max 2 replans -> ESCALATE.

Global progress rule: `progress = 5 + 20 * (collection_products_done / total_products)` (collection band: 5% to 25%).

---

## Phase 3 : ANALYSIS (lia_scan_engine via backend)

Per quadrigramme:

1. UPDATE `campaign_workflow_runs(phase='analysis')` -> `running`.
2. POST `/api/analysis/execute` with payload (see [references/analysis-phase.md](references/analysis-phase.md)):
   ```bash
   ANALYSIS_RESP=$(curl -s -X POST -H "Content-Type: application/json" -H "Authorization: Bearer ${LIA_API_TOKEN}" -d "{\"collection_id\":\"${COLLECT_BASE}/${QUAD}/${DATE}/collect\",\"taxonomy_id\":\"${TAXONOMY}\",\"quadrigramme\":\"${QUAD}\"}" http://localhost:8081/api/analysis/execute)
   ANALYSIS_ID=$(echo "${ANALYSIS_RESP}" | jq -r '.data.id // .id')
   [ -n "${ANALYSIS_ID}" ] && [ "${ANALYSIS_ID}" != "null" ] || { echo "ERROR: ${ANALYSIS_RESP}"; exit 2; }
   ```
   `TAXONOMY` = taxonomy_id for the QUAD (see reference table below).
   `COLLECT_BASE` is read from `system_variables.COLLECT_PATH` (default `/opt/lia-sec/dev/collect`).

See [SKILL_REFERENCE.md](SKILL_REFERENCE.md) -- taxonomy table and client-specific QUAD registration.

   The `-R` flag has no effect on this API call; it controls `/api/reports/merge` (Phase 4 `includeRuleReports`).
3. Poll `GET /api/analysis/{id}` every 2s. Update `grc_campaigns.progress = 25 + 40 * (analysis_pct/100)`.
4. On completion: UPDATE `campaign_workflow_runs` -> `succeeded`, metadata = {rules_applied, findings_count, duration_s}.
   Output files: the analysis engine writes intermediate results to `_alire/temp/analysis_{ANALYSIS_ID}.json` and `_alire/temp/analysis_{ANALYSIS_ID}.log`. These temp files are distinct from the final results stored in `collect/{QUAD}/{DATE}/analyse/`. See [references/analysis-phase.md](references/analysis-phase.md) for path resolution details.
5. **Log ANALYSIS_DONE** (executable, 1 per quad):
   ```bash
   log_orchestrator "INFO" "ANALYSIS_DONE" "quad=${QUAD} rules=${RULES_EXECUTED} matches=${WITH_MATCHES} duration_s=${DURATION}"
   ```
6. **Compliance engine run** (executable, 1 per quad, MANDATORY when `analyse/stats/execution_stats.json` exists):

   The lia_compliance_engine CLI maps the executed rules against every enrolled
   framework (pkg/compliance/scorer + reporter) and produces `compliance_report.json`
   consumed by the Word/PPTX exports in Phase 5. Without this step, Phase 5 will
   silently skip Section 4b "Compliance Engine Report".

   ```bash
   ENGINE_BIN=/opt/lia-sec/dev/bin/lia_compliance_engine
   RULES_DIR=/opt/lia-sec/dev/lia_rules/rule_analysis/${QUAD}
   SURVEY_DIR=/opt/lia-sec/dev/config/survey/frameworks
   ANALYSE_DIR=${COLLECT_BASE}/${QUAD}/${DATE}/analyse
   STATS_FILE=${ANALYSE_DIR}/stats/execution_stats.json
   COMPLIANCE_OUT=${ANALYSE_DIR}/compliance_report.json

   # Build on demand if binary missing or older than source
   if [ ! -x "${ENGINE_BIN}" ]; then
     env -C /opt/lia-sec/dev go build -o "${ENGINE_BIN}" ./cmd/lia_compliance_engine/ \
       || { log_orchestrator "ERROR" "COMPLIANCE_BUILD_FAILED" "quad=${QUAD}"; continue; }
   fi

   # Skip with warning if the scan produced no stats (engine requires them)
   if [ ! -f "${STATS_FILE}" ]; then
     log_orchestrator "WARN" "COMPLIANCE_SKIPPED" "quad=${QUAD} reason=missing_execution_stats path=${STATS_FILE}"
   else
     ENGINE_START=$(date +%s)
     if "${ENGINE_BIN}" --analyse-dir "${ANALYSE_DIR}" --rules-dir "${RULES_DIR}" \
           --survey-dir "${SURVEY_DIR}" --output "${COMPLIANCE_OUT}" >/tmp/compliance_${QUAD}_${DATE}.log 2>&1; then
       ENGINE_DUR=$(( $(date +%s) - ENGINE_START ))
       LOADED=$(jq -r '.summary.total_rules_loaded // 0' "${COMPLIANCE_OUT}")
       EVALD=$(jq -r '.summary.total_rules_evaluated // 0' "${COMPLIANCE_OUT}")
       WITHOUT=$(jq -r '.summary.rules_without_compliance_tags // 0' "${COMPLIANCE_OUT}")
       OVERALL=$(jq -r '.summary.overall_score // 0' "${COMPLIANCE_OUT}")
       OBSERVED=$(jq -r '.summary.score_observed_only // 0' "${COMPLIANCE_OUT}")
       log_orchestrator "INFO" "COMPLIANCE_DONE" \
         "quad=${QUAD} loaded=${LOADED} evaluated=${EVALD} without_tags=${WITHOUT} overall=${OVERALL} observed=${OBSERVED} duration_s=${ENGINE_DUR}"
     else
       log_orchestrator "ERROR" "COMPLIANCE_FAILED" \
         "quad=${QUAD} log=/tmp/compliance_${QUAD}_${DATE}.log"
       # REPLAN : not blocking -- Phase 4 MERGE continues, but Word 4b will be absent.
       # Alt1: manual rerun via `bin/lia_compliance_engine --analyse-dir ... --rules-dir ... --survey-dir ... --output ...`
       # Alt2: missing compliance tags in rules (see RulesWithoutComplianceTags in summary) -- data-level fix
     fi
   fi
   ```

   Output consumed by Phase 5 Word export via `dataMap["complianceReport"]` in `professional_export_word_audit.go` Section 4b. See `pkg/compliance/types/output.go` for the ComplianceSummary schema including `score_observed_only` and `rules_without_compliance_tags` (cycle_003 2026-04-24).

7. On 5xx: REPLAN (alt1: retry with smaller rule set via `--branch`, alt2: direct CLI `lia_scan_engine` invocation).

---

## Phase 4 : MERGE (`-R` semantics)

1. UPDATE `campaign_workflow_runs(phase='merge')` -> `running`.
2. POST `/api/reports/merge` (see [references/merge-phase.md](references/merge-phase.md)):
   ```json
   {
     "campaignIds": ["{QUAD}/{DATE}", ...],
     "includeRuleReports": true,        // true when -R flag is set
     "generateAggregated": true,
     "enableAI": {--ai bool}
   }
   ```
3. Parse response: record `totalFindings`, `globalScore`, `mergedData`.
4. On 5xx with `enableAI=true`: REPLAN with `enableAI=false` (alt1). If still 5xx: inspect `unified_logs WHERE component LIKE 'MERGE%'` for root cause (alt2).
5. **Log MERGE_DONE** (executable):
   ```bash
   log_orchestrator "INFO" "MERGE_DONE" "campaigns=${#CAMPAIGN_IDS[@]} findings=${TOTAL_FINDINGS:-0} score=${GLOBAL_SCORE:-0} ai=${AI_FLAG}"
   ```
6. `grc_campaigns.progress = 75`.

---

## Phase 5 : REPORTING (Word + Excel + PowerPoint)

1. UPDATE `campaign_workflow_runs(phase='reporting')` -> `running`.
2. POST `/api/export/professional` **four times**, iterating on `(format, reportLevel)`:
   - `(word, detailed)` -> exhaustive DOCX with per-finding Section 3 (~1.6 MB / 1500+ pages for 400+ findings)
   - `(word, executive)` -> compact DOCX for COMEX / RSSI (cover + exec summary + compliance + recommendations, no per-finding detail, ~30 KB / 25-50 pages). Saved with `_executive.docx` suffix so both levels coexist in the campaign exports dir.
   - `(excel, detailed)` -> XLSX finding list
   - `(powerpoint, detailed)` -> PPTX executive slides
   The backend endpoint switches on `request.Format` and produces a single binary per call (see `handleProfessionalExport` in `professional_export_api.go`) and reads `options.reportLevel` via `dataMap["_reportLevel"]` (injected from `config["reportLevel"]`) to gate Section 3 rendering. Looping is BLOCKING — a run that ships fewer than the 4 artefacts is INCOMPLETE. See [references/reporting-phase.md](references/reporting-phase.md).
   ```bash
   EXPORT_DIR="/opt/lia-sec/dev/collect/${PRIMARY_QUAD}/${DATE}/exports"
   mkdir -p "${EXPORT_DIR}"
   REPORT_BASENAME="LIA_${DATE}_$(IFS=_; echo "${QUADS[*]}_${DATE}")"
   declare -A EXPORT_EXT=( [word]=docx [excel]=xlsx [powerpoint]=pptx )
   # Matrix: "<format>:<reportLevel>:<filename_suffix>"
   # word:detailed produces the exhaustive audit deliverable (default suffix)
   # word:executive produces the COMEX-grade compact deliverable (_executive suffix)
   # excel + powerpoint only ship in detailed mode today
   EXPORT_MATRIX=(
     "word:detailed:"
     "word:executive:_executive"
     "excel:detailed:"
     "powerpoint:detailed:"
   )
   for ENTRY in "${EXPORT_MATRIX[@]}"; do
     IFS=':' read -r FMT LEVEL SUFFIX <<< "${ENTRY}"
     EXT="${EXPORT_EXT[${FMT}]}"
     OUT="${EXPORT_DIR}/${REPORT_BASENAME}${SUFFIX}.${EXT}"
     PAYLOAD=$(jq -n --argjson ids "$(printf '%s\n' "${CAMPAIGN_IDS[@]}" | jq -R . | jq -s .)" \
                    --arg fmt "${FMT}" --arg lvl "${LEVEL}" --arg date "${DATE}" --arg slug "${SLUG}" \
                    --argjson quads "$(printf '%s\n' "${QUADS[@]}" | jq -R . | jq -s .)" \
                    '{campaignIds:$ids, format:$fmt, options:{language:"en",reportLevel:$lvl}, auditContext:{quadrigrammes:$quads,date:$date,sessionSlug:$slug}}')
     HTTP=$(curl -s -o "${OUT}" -w "%{http_code}" -X POST "http://localhost:8081/api/export/professional" \
       -H "Content-Type: application/json" -H "Authorization: Bearer ${LIA_API_TOKEN}" -d "${PAYLOAD}")
     SIZE=$(stat -c%s "${OUT}" 2>/dev/null || echo 0)
     if [[ "${HTTP}" != "200" || "${SIZE}" -lt 1024 ]]; then
       log_orchestrator "ERROR" "REPORTING_FORMAT_FAILED" "format=${FMT} level=${LEVEL} http=${HTTP} size=${SIZE} out=${OUT}"
       continue
     fi
     log_orchestrator "INFO" "REPORTING_FORMAT_DONE" "format=${FMT} level=${LEVEL} size=${SIZE} out=${OUT}"
   done
   ```
   > Note: `auditContext.sessionSlug` is silently dropped by the Go `MergeAuditContext` struct decoder (the struct has no `sessionSlug` field). Do not rely on it being persisted server-side; store the slug locally in `FILE_TRACKER.json` instead.
3. Save returned files to `collect/${PRIMARY_QUAD}/${DATE}/exports/${REPORT_BASENAME}.{docx,xlsx,pptx}` (the same dir the Campaign Viewer UX reads). The backend also creates a row in `professional_exports` with a `file_path` pointing to `_alire/temp/exports/` — that is a backend-side side effect (out of skill scope, tracked as bug M5); the canonical artifact for UX delivery is the one in the `collect/.../exports/` directory.
4. **Sync collect data to production** (MANDATORY — production backend reads from `/opt/lia-sec/source/collect/`, not `/opt/lia-sec/dev/collect/`):
   ```bash
   for QUAD in ${QUADS}; do
     SRC="/opt/lia-sec/dev/collect/${QUAD}/${DATE}/"
     DST="/opt/lia-sec/source/collect/${QUAD}/${DATE}/"
     mkdir -p "${DST}"
     rsync -av --checksum "${SRC}" "${DST}"
     SYNCED_FILES=$(find "${DST}" -type f | wc -l)
     LogSystemEvent "INFO" "CAMPAIGN_ORCHESTRATOR" "COLLECT_SYNCED_TO_SOURCE" "${QUAD}/${DATE} -> ${SYNCED_FILES} files"
   done
   ```
   On failure: REPLAN (alt1: retry rsync with `--ignore-errors`; alt2: `cp -r` as fallback if rsync unavailable). NEVER skip this step — without it, the Campaign Viewer in the UX returns empty file trees and the DOCX report is inaccessible from production.
   > **Coverage**: the rsync is run at the `collect/{QUAD}/{DATE}/` level, so it recursively syncs ALL subdirectories in one pass: `collect/` (raw XML/JSON), `analyse/stats/`, `analyse/results/` (analysis_results.json), `analyse/logs/`, `analyse/rules_results/`, `report/` (DOCX/PPTX), `display/`, and `compliance/`. No per-subdirectory rsync is needed.
5. Mark campaign complete: `status` and `end_date` via API (in `allowedCols`); `progress = 100` via direct SQL (not exposed by PUT handler):
   ```bash
   TODAY=$(date -u +%Y-%m-%d)
   COMPLETE_RESP=$(curl -s -X PUT -H "Content-Type: application/json" -H "Authorization: Bearer ${LIA_API_TOKEN}" -d "{\"status\":\"completed\",\"end_date\":\"${TODAY}\"}" "http://localhost:8081/api/grc/campaigns/${GRC_CAMPAIGN_ID}")
   echo "${COMPLETE_RESP}" | jq -e '.success == true' > /dev/null || echo "WARN: campaign complete update non-success: ${COMPLETE_RESP}"
   psql_lia -c "UPDATE grc_campaigns SET progress = 100, updated_at = NOW() WHERE id = '${GRC_CAMPAIGN_ID}';"
   ```
6. UPDATE `campaign_workflow_runs(phase='reporting')` -> `succeeded` with metadata = {docx_path, xlsx_path, pptx_path, formats_count}.
7. **Exit gate** — all four artefacts (word detailed + word executive + xlsx + pptx) MUST exist non-empty on disk before declaring Phase 5 done:
   ```bash
   for ENTRY in "${EXPORT_MATRIX[@]}"; do
     IFS=':' read -r FMT LEVEL SUFFIX <<< "${ENTRY}"
     EXT="${EXPORT_EXT[${FMT}]}"
     F="${EXPORT_DIR}/${REPORT_BASENAME}${SUFFIX}.${EXT}"
     if [[ ! -s "${F}" ]]; then
       log_orchestrator "ERROR" "REPORTING_EXIT_GATE_FAILED" "missing=${FMT}:${LEVEL} path=${F}"
       exit 4
     fi
   done
   FORMATS_DONE=${#EXPORT_MATRIX[@]}
   ```
8. **Log REPORTING_DONE + COLLECT_SYNCED_TO_SOURCE** (executable, 2 events for Phase 5):
   ```bash
   log_orchestrator "INFO" "COLLECT_SYNCED_TO_SOURCE" "quads=${#QUADS[@]} date=${DATE} files_synced=${SYNCED_FILES}"
   log_orchestrator "INFO" "REPORTING_DONE" "export_dir=${EXPORT_DIR} formats=${FORMATS_DONE} basename=${REPORT_BASENAME}"
   ```
9. On per-format export failure: REPLAN (alt1: retry the failing format only with the same payload; alt2: skip the failing format but fail the exit gate at step 7 so the cycle cannot close silently; alt3: invoke `/pptx-recette` for a `pptx` template issue).

---

## Phase 6 : RECETTE (R17 + rule validation)

Note: this skill creates no new frontend components, so UI HELP insertion (R8) does not apply here.

1. Invoke `/recette-lia-rule` via the Skill tool on the rule set used (`lia_rules/rule_analysis/{TECH}/`). Expect exit 0 on 164 checks.
2. Playwright smoke test on `CampaignManager` with the session slug (R17 fixture + render-and-assert):
   - Open `https://liascan.tech/#/grc/campaigns` (or local VPS :3000)
   - Assert row with name `Orchestrated campaign {slug}` is present
   - Assert status chip reads `Completed` and progress bar is 100%
3. **Log RECETTE_PASS** (executable):
   ```bash
   log_orchestrator "INFO" "RECETTE_PASS" "slug=${SLUG} rules_ok=${RULES_OK} smoke_ok=${SMOKE_OK}"
   ```
4. On rule validation failure: REPLAN (alt1: fix failing rule(s) individually via `/recette-lia-rule` on the specific rule file; alt2: skip failing rules with `--exclude` flag if non-blocking, escalate if CRITICAL). See [_shared/references/recette-protocol.md](../_shared/references/recette-protocol.md).
5. On Playwright smoke failure: REPLAN (alt1: reload page and retry assertion after 5s; alt2: check `unified_logs WHERE component = 'GRC_CAMPAIGN'` for backend errors that may affect the UI).

---

## Phase 7 : COMPLETE (RETEX + Librarian Gate)

### Precondition (BLOCKING, executable)

Before any Phase 7 step, verify the previous phases actually ran. If `recovery.completed_steps`
in `FILE_TRACKER.json` does NOT include `phase_6_recette`, Phase 7 is FORBIDDEN. Retex 2026-04-24
proved that skipping this gate lets a session end in limbs (Phase 5 done, no RETEX, no close).

```bash
TRACKER="_alire/temp/campaign-orchestrator/${SLUG}/FILE_TRACKER.json"
if ! jq -e '.recovery.completed_steps | index("phase_6_recette")' "${TRACKER}" >/dev/null; then
    log_orchestrator "ERROR" "PHASE_7_BLOCKED" "slug=${SLUG} reason=phase_6_recette missing from completed_steps"
    echo "ABORT: Phase 6 RECETTE must complete before Phase 7. Loop back to Phase 6." >&2
    exit 2
fi
```

### Steps (executable list)

1. Fill RETEX from template + write to canonical path:
   ```bash
   RETEX_FILE="_alire/02_LOGS/Journals/retex/RETEX_CAMPAIGN_ORCHESTRATOR_$(date +%Y-%m-%d)_${SLUG}.md"
   envsubst < .claude/skills/campaign-orchestrator/templates/retex_console.md.tmpl > "${RETEX_FILE}"
   ```

2. **Display** the RETEX content in the conversation (operator reads it, flags it):
   ```bash
   cat "${RETEX_FILE}"
   # Operator MUST set this flag after reading. Without it, exit gate fails.
   export RETEX_DISPLAYED=1
   ```

3. Update `_alire/tracking/INDEX.md` with plan + RETEX lines (section APEX or Campaign). Use the
   existing format of other entries. The exit gate greps for both file names.

4. Append a final entry to `decision_log.jsonl`:
   ```bash
   DLOG="_alire/temp/campaign-orchestrator/${SLUG}/decision_log.jsonl"
   jq -n --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" --arg slug "${SLUG}" \
     '{timestamp:$ts, action:"CAMPAIGN_COMPLETE", session:$slug, outcome:"success", confidence:"high"}' >> "${DLOG}"
   ```

5. Librarian audit (non-blocking, warn only):
   ```bash
   python3 .claude/skills/doc-code/scripts/doc_librarian.py audit _alire/01_DOCUMENTATION/ || true
   ```

6. Verify PLAN copy exists (created in Phase 0). If absent, copy from template:
   ```bash
   PLAN_FILE="_alire/tracking/PLAN_CAMPAIGN_ORCHESTRATOR_${SLUG}_$(date +%Y-%m-%d).md"
   [ -f "${PLAN_FILE}" ] || cp .claude/skills/campaign-orchestrator/templates/PLAN_CAMPAIGN_ORCHESTRATOR.md.tmpl "${PLAN_FILE}"
   ```

7. Stage and commit plan + RETEX + decision_log (no `reports/` per R7). Push if < 5 unpushed commits.

### Exit gate (BLOCKING, 4 proofs)

The cycle CANNOT be declared complete until these 4 proofs pass. Retex 2026-04-24 : Phase 7
was documented but none of the artifacts were verified, so the skill "completed" in limbo.

```bash
phase7_exit_gate() {
    local FAILED=0

    # Proof 1 : RETEX file exists on disk
    [ -f "${RETEX_FILE}" ] && [ -s "${RETEX_FILE}" ] || {
        echo "GATE-FAIL: RETEX file missing or empty: ${RETEX_FILE}" >&2; FAILED=1; }

    # Proof 2 : RETEX displayed in conversation (operator sets this flag after reading)
    [ "${RETEX_DISPLAYED:-0}" = "1" ] || {
        echo "GATE-FAIL: RETEX_DISPLAYED=1 not set. Operator must read the RETEX and export the flag." >&2; FAILED=1; }

    # Proof 3 : INDEX.md references the plan and the retex of this slug
    grep -q "${SLUG}" _alire/tracking/INDEX.md || {
        echo "GATE-FAIL: _alire/tracking/INDEX.md does not reference ${SLUG}" >&2; FAILED=1; }

    # Proof 4 : unified_logs has >= 18 events for this slug
    local EVENT_COUNT
    EVENT_COUNT=$(psql_lia -tAc "SELECT COUNT(*) FROM unified_logs WHERE component = 'CAMPAIGN_ORCHESTRATOR' AND message LIKE '%${SLUG}%' AND timestamp >= NOW() - INTERVAL '24 hours';")
    if [ "${EVENT_COUNT:-0}" -lt 18 ]; then
        echo "GATE-FAIL: only ${EVENT_COUNT} CAMPAIGN_ORCHESTRATOR events for slug ${SLUG}, expected >= 18" >&2
        FAILED=1
    fi

    if [ "${FAILED}" -eq 1 ]; then
        log_orchestrator "ERROR" "PHASE_7_FAILURE" "slug=${SLUG} exit_gate=FAILED events=${EVENT_COUNT} retex_displayed=${RETEX_DISPLAYED:-0}"
        return 1
    fi

    log_orchestrator "INFO" "CAMPAIGN_COMPLETE" "slug=${SLUG} events=${EVENT_COUNT} retex=${RETEX_FILE}"
    return 0
}

phase7_exit_gate || exit 3
```

On gate failure : fix the missing proof, rerun the gate. NEVER bypass. The cycle must either
pass the gate or be explicitly aborted with `PHASE_7_FAILURE` logged.

---

## Autonomy perimeter

Inherits `_shared/references/agentic-core.md` section 2. Campaign-specific rules:

| Action | Autonomous | Escalate |
|--------|------------|----------|
| INSERT `grc_campaigns` + UPDATE status | YES | - |
| INSERT `campaign_workflow_runs` (if table exists) | YES | - |
| Run collection scripts in sandboxed containers or on VPS itself | YES | - |
| Call `lia_scan_engine` via `/api/analysis/execute` | YES | - |
| Call `/api/reports/merge` | YES | - |
| Apply migration `101_campaign_workflow_runs.sql` | **NO** | Always escalate (R5 DDL) |
| Create dashboard React component | **NO** | Delegate to `/react-expert` via `/apex` (v2 mode) |
| Delete a `grc_campaigns` row | **NO** | Always escalate |
| Modify `merge_api.go` or `lia_scan_engine` source | **NO** | Always escalate |

---

## Agentic criteria C1-C5

### C1 Decomposition

Subtasks are atomic and independently replanable: 4 phases x N products = up to 16 units. Each `COLLECT[product]` retries without affecting others. Phase dependencies explicit: `COLLECTION -> ANALYSIS -> MERGE -> REPORTING -> RECETTE`.

Each subtask is tagged with a complexity label in the PLAN file (`PLAN_CAMPAIGN_ORCHESTRATOR_{slug}_{YYYY-MM-DD}.md`):

| Label | Meaning | Typical duration | Model |
|-------|---------|------------------|-------|
| TRIVIAL  | mkdir, SQL UPDATE, file move, polling tick | < 5 s | haiku |
| MODERATE | script invocation, API call + parsing, fixture capture | 5 s - 3 min | haiku/sonnet |
| COMPLEX  | analysis engine run, merge with AI, REPLAN selection | 3 min - 15 min | sonnet/opus |

Default mapping for this skill:
- Phase 0 INIT / Phase 1 OBSERVE UPDATE steps -> TRIVIAL
- Phase 2 COLLECTION per product -> MODERATE
- Phase 3 ANALYSIS per quad, Phase 4 MERGE, Phase 5 REPORTING -> COMPLEX
- Phase 6 RECETTE (recette-lia-rule + Playwright smoke) -> MODERATE
- Phase 7 COMPLETE (RETEX + Librarian Gate) -> TRIVIAL

### C2 Planification

`PLAN_CAMPAIGN_ORCHESTRATOR_{slug}_{YYYY-MM-DD}.md` is created at Phase 0 before any DB write or script execution. Template in `templates/PLAN_CAMPAIGN_ORCHESTRATOR.md.tmpl`. The plan includes:
- Pre-flight checklist (ticked)
- Kanban per (phase, product) with status `[ ]` / `[x]`
- Decision log pointer
- Empty RETEX section filled at COMPLETE

### C3 Replanification

Each subtask emits an explicit EVALUATE classification after ACT+OBSERVE:

| Classification | Trigger | Decision |
|----------------|---------|----------|
| **SUCCESS** | actual output matches expected output | log to `action_journal.jsonl`, tick `[x]` in PLAN, move to next subtask |
| **PARTIAL** | partial match (e.g. 3 of 4 products collected; rules applied but findings below threshold) | retry with adjustment OR accept + continue + document in `decision_log.jsonl` |
| **FAILURE** | actual does not match expected (script non-zero, 5xx, empty output, timeout) | trigger REPLAN |

Max 2 REPLAN per subtask. Each REPLAN:
- Documented in `decision_log.jsonl` with `alternatives_rejected`
- At least 2 alternatives evaluated before selection
- Never repeats the same failed action (at least one variable changes: flag, retry, fallback tool)

Common REPLAN patterns:
- Missing script -> delegate `/create-collect-script`
- Binary absent -> `./cmd/sigma_web/build_secure_lia.sh`
- Merge 5xx with AI -> retry with `enableAI=false`
- Analysis 5xx -> direct CLI fallback with `lia_scan_engine`

After 3 consecutive REPLAN failures on the same subtask: ESCALATE to user.

### C4 Outillage (model selection)

| Task | Model |
|------|-------|
| SQL UPDATE progress / status polling | haiku |
| Script invocation + output parsing | haiku |
| Merge error diagnosis (parse `unified_logs`) | sonnet |
| RETEX synthesis (final) | sonnet |
| Architecture decision (apply migration 101? create dashboard v2?) | opus (orchestrator, never delegated) |

### C5 Tracabilite (3 levels)

1. **Working**: `_alire/temp/campaign-orchestrator/{slug}/action_journal.jsonl`, `FILE_TRACKER.json`, `decision_log.jsonl`.
2. **Application**: `LogSystemEvent("INFO"|"ERROR", "CAMPAIGN_ORCHESTRATOR", "{ACTION}", "{details}")` -> `unified_logs`.
3. **Business**: rows in `grc_campaigns` (+ `campaign_workflow_runs` if v2), surfaced to the user in `CampaignManager` and `LogManager`.

#### FILE_TRACKER.json schema

Created at Phase 0 INIT, updated at each phase transition, never deleted mid-run.

```json
{
  "schema": "campaign-orchestrator-file-tracker-v1",
  "slug": "<string, required>",
  "date": "<string YYYYMMDD, required>",
  "quads": ["<QUAD1>", "<QUAD2>"],
  "flags": {
    "dry_run": "<bool, required>",
    "with_ai": "<bool, required>",
    "include_rule_reports": "<bool, required>",
    "resume": "<bool>",
    "resume_from": "<string|null>"
  },
  "phase_states": {
    "phase_0": "<idle|running|succeeded|failed, required>",
    "phase_1": "<idle|running|succeeded|failed, required>",
    "phase_2": "<idle|running|succeeded|failed, required>",
    "phase_3": "<idle|running|succeeded|failed, required>",
    "phase_4": "<idle|running|succeeded|failed, required>",
    "phase_5": "<idle|running|succeeded|failed>",
    "phase_6": "<idle|running|succeeded|failed>",
    "phase_7": "<idle|running|succeeded|failed>"
  },
  "artifacts": {
    "collect_dirs": ["<path per QUAD, optional>"],
    "analysis_ids": {"<QUAD>": "<UUID|null>"},
    "merge_id": "<UUID|null>",
    "report_path": "<string|null>",
    "retex_path": "<string|null>"
  },
  "replan_counts": {"<phase_key>": "<int>"},
  "last_updated": "<ISO8601, required>"
}
```

Required fields: `schema`, `slug`, `date`, `quads`, `flags.dry_run`, `flags.with_ai`, `flags.include_rule_reports`, all `phase_states.*`, `last_updated`.
Optional fields: `artifacts.*`, `replan_counts`, `flags.resume`, `flags.resume_from`.

#### FILE_TRACKER.json filled example

Mid-run state snapshot: Phase 0-2 succeeded, Phase 3 ANALYSIS in progress, one REPLAN occurred during docker collection.

```json
{
  "schema": "campaign-orchestrator-file-tracker-v1",
  "slug": "co-20260422-143012-adds",
  "date": "20260422",
  "quads": ["ADDS"],
  "flags": {
    "dry_run": false,
    "with_ai": true,
    "include_rule_reports": true,
    "resume": false,
    "resume_from": null
  },
  "phase_states": {
    "phase_0": "succeeded",
    "phase_1": "succeeded",
    "phase_2": "succeeded",
    "phase_3": "running",
    "phase_4": "idle",
    "phase_5": "idle",
    "phase_6": "idle",
    "phase_7": "idle"
  },
  "artifacts": {
    "collect_dirs": ["/opt/lia-sec/dev/collect/ADDS/20260422/collect"],
    "analysis_ids": {"ADDS": "3a7f1c2e-0d45-4b89-a123-def012345678"},
    "merge_id": null,
    "report_path": null,
    "retex_path": null
  },
  "replan_counts": {"phase_2_docker": 1},
  "last_updated": "2026-04-22T14:32:07Z"
}
```

`merge_id` and `report_path` are null because Phase 4-5 have not run yet. `replan_counts.phase_2_docker: 1` documents a docker collection script that exited non-zero and was rerun with `--verbose` (REPLAN alt1).

RETEX **displayed in console** at COMPLETE is mandatory (per user feedback `feedback_retex_display_mandatory.md`).

---

## Pre-requisites

### Required environment variables

The following variables MUST be exported before invoking the skill. None are hardcoded.

| Variable | Purpose | Example value |
|----------|---------|---------------|
| `LIA_API_TOKEN` | JWT bearer token for all REST calls | `eyJhbGci...` (from login response) |
| `LIA_DB_PASS` | PostgreSQL password | (from VPS systemd unit or `.env`) |
| `LIA_DB_USER` | PostgreSQL user | `lia_admin` |
| `LIA_DB_NAME` | PostgreSQL database | `lia_scan` |
| `LIA_DB_HOST` | PostgreSQL host | `localhost` |
| `LIA_DB_PORT` | PostgreSQL port | `5432` |

Obtain `LIA_API_TOKEN` via:
```bash
TOKEN_RESP=$(curl -s -X POST -H "Content-Type: application/json" -d '{"email":"admin@liascan.tech","password":"..."}' http://localhost:8081/api/auth/login)
export LIA_API_TOKEN=$(echo "${TOKEN_RESP}" | jq -r '.token')
```

Obtain `LIA_DB_PASS` from the systemd unit on the VPS:
```bash
export LIA_DB_PASS=$(systemctl cat lia-backend 2>/dev/null | grep LIA_DB_PASS | cut -d= -f2)
```

### psql_lia() helper (required by all phases)

Define this helper once at session start before running any phase:

```bash
export LIA_DB_USER="${LIA_DB_USER:-lia_admin}"
export LIA_DB_NAME="${LIA_DB_NAME:-lia_scan}"
export LIA_DB_HOST="${LIA_DB_HOST:-localhost}"
export LIA_DB_PORT="${LIA_DB_PORT:-5432}"

psql_lia() {
  PGPASSWORD="${LIA_DB_PASS}" psql -h "${LIA_DB_HOST}" -p "${LIA_DB_PORT}" -U "${LIA_DB_USER}" -d "${LIA_DB_NAME}" "$@"
}
```

### Other requirements

- `/opt/lia-sec/dev/bin/lia_scan_engine` present and executable (rebuilt via `./cmd/sigma_web/build_secure_lia.sh` if absent).
- Backend up: `curl -s http://localhost:8081/api/health` returns 200. R9: use `./cleanup_services.sh status` first.
- PostgreSQL accessible: `psql_lia -c "SELECT 1"` exits 0.
- Collection scripts present for each product requested (verified in Phase 0).
- `_alire/tracking/INDEX.md` exists (Librarian gate).

---

## End-to-end verification

See [SKILL_REFERENCE.md](SKILL_REFERENCE.md) -- end-to-end verification queries.

---

## Out of scope

See [SKILL_REFERENCE.md](SKILL_REFERENCE.md) -- out-of-scope list.

---

## Conformity

Respects: R1 (git discipline), R5 (PostgreSQL first, no DDL auto), R6 (LogSystemEvent only), R7 (temp in `_alire/temp/`), R9 (cleanup_services.sh), R10 (no emoji), R12 (English in files), R14 (infra changes documented), R15 (doc librarian), R17 (contract gate via Playwright smoke).

---

## File freshness policy

**Split threshold**: when `SKILL.md` exceeds 600 lines, the file MUST be split to maintain readability.

**Core flow stays in `SKILL.md`** (target: < 500 lines post-split):
- Phase descriptions 0-7 (the sequential operational loop)
- Pre-requisites section
- FILE_TRACKER.json schema + filled example
- Edge case matrix and multi-QUAD invocation example
- Conformity section

**Reference material lives in `SKILL_REFERENCE.md`** (companion file):
- Full QUAD-to-taxonomy_id reference table
- Client-specific QUAD registration procedure
- End-to-end verification steps
- Out-of-scope list

**Current state**: split applied 2026-04-22 (cycle 4). SKILL.md points to SKILL_REFERENCE.md for moved sections.
