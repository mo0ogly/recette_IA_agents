# Campaign Orchestrator -- Reference Material

Companion file to [SKILL.md](SKILL.md). Contains reference tables, verification queries, and scope boundaries.

---

## Taxonomy ID reference per QUAD

**taxonomy_id = the QUAD name itself** (verified 2026-04-23 against `config/taxonomy/` directory).
`extractQuadrigramFromTaxonomy()` in `analysis_engine_helpers.go` resolves `{QUAD}` ->
`config/taxonomy/{QUAD}_taxonomy.json`, so passing the QUAD directly always works.

| QUAD | `taxonomy_id` (= QUAD name) | Technology | Taxonomy file |
|------|-----------------------------|------------|---------------|
| ADDS | `ADDS` | Windows Active Directory | `ADDS_taxonomy.json` |
| EXCH | `EXCH` | Microsoft Exchange Server | `EXCH_taxonomy.json` |
| DOCK | `DOCK` | Docker / container environments | `DOCK_taxonomy.json` |
| LINX | `LINX` | Linux servers | `LINX_taxonomy.json` |
| MSSQL | `MSSQL` | Microsoft SQL Server | `MSSQL_taxonomy.json` |
| POSTGRESQL | `POSTGRESQL` | PostgreSQL databases | `POSTGRESQL_taxonomy.json` |
| KUBE | `KUBE` | Kubernetes clusters | `KUBE_taxonomy.json` |
| VCNT | `VCNT` | VMware vCenter / ESXi | `VCNT_taxonomy.json` |
| AZUR | `AZUR` | Microsoft Azure tenant | `AZUR_taxonomy.json` |
| UB25 | `UB25` | Ubuntu 25 / Linux CIS | `UB25_taxonomy.json` |
| GO | `GO` | Go application environments | `GO_taxonomy.json` |

**IMPORTANT -- wrong QUADs to never use:**
- `LNXS` does NOT exist -> use `LINX`
- `MSSQ` does NOT exist -> use `MSSQL`
- `PSQL` does NOT exist -> use `POSTGRESQL`

To verify a taxonomy file exists before Phase 3:
```bash
ls /opt/lia-sec/dev/config/taxonomy/${QUAD}_taxonomy.json || { echo "ERROR: no taxonomy for ${QUAD}"; exit 2; }
```

For QUADs not in this table, check the filesystem first:
```bash
ls /opt/lia-sec/dev/config/taxonomy/ | grep -i "${QUAD}"
```
Never hardcode an invented taxonomy_id. If no file exists, create it following existing Format B
(list format with `quadrigram` field) before running Phase 3.

### Client-specific QUAD registration

Some deployments use non-standard QUADs (client codenames, discovery targets, fallback collections) that do not appear in the generic table above. Procedure:

1. **Discover the existing taxonomy_id**: `psql_lia -c "SELECT DISTINCT taxonomy_id, name FROM available_surveys ORDER BY taxonomy_id;"` -- look for the closest match by technology family.
2. **If no close match exists**: identify the parent technology (e.g. a custom QUAD `CLNT` scanning Windows AD -> closest match is `ADDS`). Map to `taxonomy_id = 'ADDS'`.
3. **Register the mapping**: add an entry to `pdca/{scope}/cycle_N/quad_taxonomy_map.json`:
   ```json
   { "quad": "CLNT", "taxonomy_id": "ADDS", "reason": "Windows AD client-specific QUAD", "registered": "2026-04-22" }
   ```
4. **Create taxonomy config**: ensure `collect/{QUAD}/` directory structure exists and `available_surveys` has a row (or reuse the parent taxonomy_id in the API call body directly).
5. **Verify**: `psql_lia -c "SELECT COUNT(*) FROM available_surveys WHERE taxonomy_id = 'ADDS';"` must return > 0 before Phase 3 starts.

If no taxonomy match is found after steps 1-2, escalate (do not invent an ID): query `grc_campaigns` for previous successful runs of the same QUAD to extract the `taxonomy_id` used historically.

---

## End-to-end verification (after first run)

1. `psql`: `SELECT id, name, status, progress FROM grc_campaigns WHERE metadata->>'session_slug' = '{slug}';` -> status `completed`, progress 100.
2. `psql`: `SELECT level, action, details FROM unified_logs WHERE component = 'CAMPAIGN_ORCHESTRATOR' AND details LIKE '%{slug}%' ORDER BY created_at;` -> phases in order INIT -> OBSERVE -> COLLECTION_DONE (x N products) -> ANALYSIS_DONE -> MERGE_DONE -> REPORTING_DONE -> RECETTE_PASS.
3. Filesystem: `ls campaigns/{QUAD}/{DATE}/` lists `{PRODUCT}/` subfolders with non-empty `test_data.json`.
4. Filesystem: `_alire/temp/campaign-orchestrator/{slug}/reports/{QUAD}_{DATE}.pptx` exists (>= 50 KB for a real run).
5. UX: open `https://liascan.tech/#/grc/campaigns`, see the row with `completed` chip. Open `LogManager` filtered on `component=CAMPAIGN_ORCHESTRATOR` and see the phase timeline.
6. `_alire/02_LOGS/Journals/retex/RETEX_CAMPAIGN_ORCHESTRATOR_*.md` present. `_alire/tracking/INDEX.md` updated.

---

## Out of scope (do NOT auto-apply)

- Migration `101_campaign_workflow_runs.sql` (delivered as template, never applied by the skill).
- Creation of `CampaignOrchestrationDashboard.tsx` (v2, delegated to `/apex` + `/react-expert` only on explicit user request).
- Modification of `merge_api.go`, `lia_scan_engine`, or any existing Go file.
- Creation of new collection scripts (delegate to `/create-collect-script` on missing script).
- Production deployment (the skill runs on the VPS itself; deploy.sh is NOT invoked).
