-- Migration 101 : campaign_workflow_runs
-- Purpose : unified per-phase x per-product tracking for campaign-orchestrator skill.
-- Status  : OPTIONAL v2 -- not auto-applied by the skill.
-- Apply   : via /db-schema-designer workflow only, on explicit user request.
-- Safety  : uses IF NOT EXISTS; idempotent; no destructive DDL.
-- Conventions : R5 (UUID PK, TIMESTAMPTZ, JSONB, GIN, no FLOAT).

BEGIN;

CREATE TABLE IF NOT EXISTS campaign_workflow_runs (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_slug     TEXT NOT NULL,
    quadrigrammes   TEXT[] NOT NULL,
    products         TEXT[] NOT NULL,
    campaign_date    DATE NOT NULL,
    grc_campaign_id  UUID REFERENCES grc_campaigns(id) ON DELETE CASCADE,

    phase           TEXT NOT NULL
        CHECK (phase IN ('collection','analysis','merge','reporting')),
    phase_status    TEXT NOT NULL DEFAULT 'pending'
        CHECK (phase_status IN ('pending','running','succeeded','failed','skipped')),
    progress_pct    SMALLINT DEFAULT 0
        CHECK (progress_pct BETWEEN 0 AND 100),

    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    error_message   TEXT,

    metadata        JSONB NOT NULL DEFAULT '{}'::JSONB,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cwr_session_phase
    ON campaign_workflow_runs(session_slug, phase);

CREATE INDEX IF NOT EXISTS idx_cwr_grc_campaign
    ON campaign_workflow_runs(grc_campaign_id);

CREATE INDEX IF NOT EXISTS idx_cwr_metadata_gin
    ON campaign_workflow_runs USING GIN (metadata);

CREATE INDEX IF NOT EXISTS idx_cwr_status_started
    ON campaign_workflow_runs(phase_status, started_at DESC);

COMMENT ON TABLE campaign_workflow_runs IS
    'Per-phase per-product tracking for end-to-end orchestrated audit campaigns.';

COMMENT ON COLUMN campaign_workflow_runs.session_slug IS
    'Correlation key across rows of the same orchestrator run.';

COMMENT ON COLUMN campaign_workflow_runs.metadata IS
    'Phase-specific details: for collection = {product, output_path, test_data_size_bytes, exit_code}; for analysis = {quadrigramme, analysis_id, findings_count, rules_applied, duration_seconds}; for merge = {total_findings, total_rules, global_score, include_rule_reports, enable_ai, merge_result_path}; for reporting = {pptx_path, json_path, pptx_size_bytes, slide_count}.';

COMMIT;
