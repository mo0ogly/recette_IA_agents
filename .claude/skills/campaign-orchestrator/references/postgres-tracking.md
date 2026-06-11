# PostgreSQL Tracking -- Tables, Patterns, and Optional v2 Migration

## Tables used (all existing, no DDL required in v1)

| Table | Migration | Role in orchestrator |
|-------|-----------|----------------------|
| `grc_campaigns` | `033_campaigns.sql` | Master row per campaign run. Status lifecycle: `draft` -> `running` -> `completed` or `failed`. Progress 0-100. |
| `batch_wave_runs` | `015_batch_tracking.sql` | Optional per-wave tracking (kept for compatibility with batch CVE pipeline). Not written by orchestrator v1. |
| `lia_auto_jobs` | `013_auto_jobs_tracking.sql` | Optional per-script run. Not written by orchestrator v1 (used by CVE auto-jobs). |
| `unified_logs` | core | All log events via `LogSystemEvent`. R6 mandatory. |
| `campaign_workflow_runs` | `101_*.sql` (template, NOT applied) | v2: phase x product grid for unified dashboard. |

## INSERT grc_campaigns (Phase 1 OBSERVE)

```sql
INSERT INTO grc_campaigns (
  id, name, description, client_id, status,
  start_date, progress, created_by,
  metadata, created_at, updated_at
) VALUES (
  gen_random_uuid(),
  'Orchestrated campaign ' || $1,                  -- session_slug
  'Products: ' || $2 || ' | Quads: ' || $3 ||
  ' | -R: ' || $4 || ' | AI: ' || $5,
  NULL,                                            -- client_id optional
  'draft',
  $6::date,                                        -- campaign_date
  0,
  'campaign-orchestrator',
  jsonb_build_object(
    'session_slug', $1,
    'products', $7::jsonb,                         -- array of products
    'quadrigrammes', $8::jsonb,                    -- array of quads
    'include_rule_reports', $4::bool,
    'enable_ai', $5::bool,
    'source_skill', 'campaign-orchestrator',
    'skill_version', '1.0'
  ),
  NOW(), NOW()
)
RETURNING id;
```

## UPDATE grc_campaigns.progress (throughout the workflow)

Expected progression:

| Phase | Target progress |
|-------|-----------------|
| OBSERVE done | 5 |
| COLLECTION (per product done) | 5 + 20 * (done / total) |
| ANALYSIS (per quad done) | 25 + 40 * (done / total) |
| MERGE done | 75 |
| REPORTING done | 100 (status -> `completed`) |

```sql
UPDATE grc_campaigns
SET progress = $1::int,
    status = CASE WHEN $1 >= 100 THEN 'completed' ELSE 'running' END,
    updated_at = NOW(),
    end_date = CASE WHEN $1 >= 100 THEN CURRENT_DATE ELSE end_date END
WHERE id = $2;
```

## Failure path

```sql
UPDATE grc_campaigns
SET status = 'failed',
    updated_at = NOW(),
    metadata = metadata || jsonb_build_object(
      'failed_phase', $2,
      'error_message', $3,
      'failed_at', to_char(NOW(), 'YYYY-MM-DD"T"HH24:MI:SSOF')
    )
WHERE id = $1;
```

## SELECT for UX polling

The React frontend (CampaignManager) calls `GET /api/campaigns/batch/{id}/status` which reads `grc_campaigns` and returns `{success: true, data: {id, status, progress, metadata}}`. No custom endpoint needed for v1.

For session-specific polling (direct SQL, from the skill):
```sql
SELECT id, name, status, progress,
       metadata->>'session_slug' AS session_slug,
       updated_at
FROM grc_campaigns
WHERE metadata->>'session_slug' = $1
LIMIT 1;
```

## Pattern: run SQL from the skill

Use the `psql_lia()` helper pattern (see `.claude/rules/no-hardcoded-secrets.md`):

```bash
psql_lia() {
  PGPASSWORD="$LIA_DB_PASS" psql -h "$LIA_DB_HOST" -p "$LIA_DB_PORT" \
    -U "$LIA_DB_USER" -d "$LIA_DB_NAME" "$@"
}

# Example: insert grc_campaigns row
GRC_ID=$(psql_lia -tAc "
  INSERT INTO grc_campaigns (id, name, status, start_date, progress, metadata, created_by, created_at, updated_at)
  VALUES (gen_random_uuid(),
          'Orchestrated campaign ${SLUG}',
          'draft',
          '${DATE_ISO}',
          0,
          jsonb_build_object('session_slug', '${SLUG}'),
          'campaign-orchestrator',
          NOW(), NOW())
  RETURNING id;
")
```

`LIA_DB_PASS` and related variables must be set via environment (never in the skill code).

## Optional v2: migration 101

File: `templates/migration_101_campaign_workflow_runs.sql` (provided, NOT auto-applied).

```sql
CREATE TABLE IF NOT EXISTS campaign_workflow_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_slug TEXT NOT NULL,
  quadrigrammes TEXT[] NOT NULL,
  products TEXT[] NOT NULL,
  campaign_date DATE NOT NULL,
  grc_campaign_id UUID REFERENCES grc_campaigns(id) ON DELETE CASCADE,
  phase TEXT NOT NULL CHECK (phase IN ('collection','analysis','merge','reporting')),
  phase_status TEXT NOT NULL CHECK (phase_status IN ('pending','running','succeeded','failed','skipped')),
  progress_pct SMALLINT CHECK (progress_pct BETWEEN 0 AND 100),
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  error_message TEXT,
  metadata JSONB DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cwr_session_phase
  ON campaign_workflow_runs(session_slug, phase);
CREATE INDEX IF NOT EXISTS idx_cwr_grc_campaign
  ON campaign_workflow_runs(grc_campaign_id);
CREATE INDEX IF NOT EXISTS idx_cwr_metadata_gin
  ON campaign_workflow_runs USING GIN (metadata);
```

Conventions respected:
- UUID PK (R5)
- TIMESTAMPTZ (R5)
- JSONB (R5)
- GIN index on JSONB (R5)
- No FLOAT (R5)
- `IF NOT EXISTS` (safe reapply)
- CHECK constraints on enums

Apply via `/db-schema-designer` when the user explicitly requests v2. Never apply silently.

## Verification queries

After a run:

```sql
-- Campaign status
SELECT id, name, status, progress, metadata->>'session_slug' AS slug
FROM grc_campaigns
WHERE metadata->>'session_slug' = '{slug}';

-- Log timeline
SELECT created_at, level, action, details
FROM unified_logs
WHERE component = 'CAMPAIGN_ORCHESTRATOR'
  AND details LIKE '%{slug}%'
ORDER BY created_at ASC;

-- Phase tracking (v2 only)
SELECT phase, phase_status, progress_pct, started_at, completed_at,
       metadata->>'product' AS product, error_message
FROM campaign_workflow_runs
WHERE session_slug = '{slug}'
ORDER BY phase, started_at;
```
