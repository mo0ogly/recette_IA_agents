# Merge Phase -- `/api/reports/merge` and the `-R` Flag

## Endpoint and source of truth

- Handler: `cmd/sigma_web/merge_api.go`
- Payload struct: `MergeRequest` (file line 12-19)
- AI-enhanced response struct: `MergeResult` with `AIInsights` (same file)
- Verified field: `IncludeRuleReports bool  \`json:"includeRuleReports"\`` at `cmd/sigma_web/merge_api.go:14`

## MergeRequest payload

```json
{
  "campaignIds": ["ADDS/20260419", "LINX/20260419", "PGSQ/20260419"],
  "includeRuleReports": true,
  "generateAggregated": true,
  "enableAI": false,
  "auditContext": {
    "auditor": "campaign-orchestrator",
    "clientName": "",
    "auditType": "automated",
    "sessionSlug": "co-20260419-103000-adds-linx-pgsq"
  }
}
```

Field mapping from orchestrator flags:

| Orchestrator | MergeRequest field | Notes |
|--------------|--------------------|-------|
| `-R` / `--include-rule-reports` | `includeRuleReports: true` | BLOCKING: always send this boolean. Default `false` when `-R` absent |
| `--ai` | `enableAI: true` | Triggers AI insights generation (LogSystemEvent on failure) |
| `--products <list>` | Implied in `campaignIds` via the product subfolders collected | - |
| Session slug | `auditContext.sessionSlug` | Enables UX deeplinks + correlation with `unified_logs` |

## Campaign ID format

The `campaignIds` array expects `"QUAD/DATE"` strings, one per quadrigramme analyzed. The merge endpoint reads the analysis outputs stored under `campaigns/{QUAD}/{DATE}/` (aggregated by the analysis phase) or the JSON files the orchestrator wrote to `_alire/temp/campaign-orchestrator/{slug}/analysis/{QUAD}.json`.

Verify the endpoint's expected location in the backend source; if only one format is accepted, use that one consistently.

## Invocation

```bash
MERGE_PAYLOAD=$(jq -n \
  --argjson ids "${CAMPAIGN_IDS_JSON}" \
  --argjson rules_reports "${INCLUDE_RULE_REPORTS}" \
  --argjson ai "${ENABLE_AI}" \
  --arg slug "${SLUG}" \
  '{
    campaignIds: $ids,
    includeRuleReports: $rules_reports,
    generateAggregated: true,
    enableAI: $ai,
    auditContext: {
      auditor: "campaign-orchestrator",
      auditType: "automated",
      sessionSlug: $slug
    }
  }')

MERGE_RESP=$(curl -s -X POST \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${LIA_API_TOKEN}" \
  -d "${MERGE_PAYLOAD}" \
  http://localhost:8081/api/reports/merge)

# Save the raw merge result
echo "${MERGE_RESP}" > _alire/temp/campaign-orchestrator/${SLUG}/merge/result.json

# Unwrap envelope (R17): the backend returns {success, data}
MERGED_DATA=$(echo "${MERGE_RESP}" | jq '.data')
TOTAL_FINDINGS=$(echo "${MERGED_DATA}" | jq '.totalFindings')
GLOBAL_SCORE=$(echo "${MERGED_DATA}" | jq '.globalScore')
```

## Response parsing (MergeResult)

Key fields from `MergeResult` struct:
- `TotalCampaigns` int
- `TotalFindings` int
- `TotalRules` int
- `GlobalScore` float64
- `MergedData` map[string]interface{}
- `AIInsights` optional pointer (only when `enableAI = true`)
- `MergedFindings` []MergedFinding
- `RuleRecommendations` []RuleRecommendation

When `includeRuleReports: true`, `RuleRecommendations` is populated; otherwise empty.

## PostgreSQL tracking

```sql
UPDATE campaign_workflow_runs
SET phase_status = 'running', started_at = NOW()
WHERE session_slug = $1 AND phase = 'merge';

-- On success
UPDATE campaign_workflow_runs
SET phase_status = 'succeeded',
    completed_at = NOW(),
    progress_pct = 100,
    metadata = metadata || jsonb_build_object(
      'total_findings', $2::int,
      'total_rules', $3::int,
      'global_score', $4::numeric,
      'include_rule_reports', $5::bool,
      'enable_ai', $6::bool,
      'merge_result_path', $7
    )
WHERE session_slug = $1 AND phase = 'merge';

-- Campaign-level progress
UPDATE grc_campaigns
SET progress = 75
WHERE id = $1;
```

## Logging

```
LogSystemEvent("INFO", "CAMPAIGN_ORCHESTRATOR", "MERGE_START",
   fmt.Sprintf("slug=%s campaigns=%d R=%t AI=%t", slug, len(ids), includeRR, enableAI))

LogSystemEvent("INFO", "CAMPAIGN_ORCHESTRATOR", "MERGE_DONE",
   fmt.Sprintf("slug=%s findings=%d rules=%d score=%.2f", slug, findings, rules, score))
```

## REPLAN patterns

1. **HTTP 500 with `enableAI: true`** (most common failure mode):
   - Alt 1: retry with `enableAI: false` (the merge itself still works, AI insights are optional).
   - Alt 2: inspect `unified_logs WHERE component IN ('MERGE_AI','MERGE_API') AND level = 'ERROR'`.
2. **HTTP 404 on one of the `campaignIds`**: a quadrigramme failed to analyze. Do not merge that one; retry with the remaining ids.
3. **Empty `mergedData`**: the analysis produced zero findings. Record as success with `metadata.total_findings = 0`; user-visible note in RETEX.
4. **Timeout on large merge** (>3 campaigns): retry sequentially (one pair at a time) and aggregate client-side.

Max 2 REPLAN on merge before ESCALATE.

## Note on AI usage

`enableAI: true` routes through `ExecuteWithRAG` per R22. The orchestrator does NOT bypass this path. If the AI response is unsatisfactory (empty, generic), that is a prompt template issue to be fixed via `/rag-architect`, NOT by adding a local fallback.
