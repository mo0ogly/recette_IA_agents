# UX Visibility -- Deeplinks, Polling, and Optional v2 Dashboard

## v1: existing UX (no new component needed)

The user sees the campaign progress in THREE existing screens, all reading the same PostgreSQL rows and `unified_logs` entries the orchestrator writes.

### 1. CampaignManager (GRC admin)

- Route: `https://liascan.tech/#/grc/campaigns` (prod) or `http://localhost:3000/#/grc/campaigns` (local)
- Component: `sigma-react-frontend/src/components/grc/CampaignManager.tsx`
- What the user sees:
  - Row with `name = "Orchestrated campaign {slug}"`
  - Status chip: `draft` -> `running` -> `completed` (or `failed`)
  - Progress bar reflecting `grc_campaigns.progress` 0-100
  - Created-by: `campaign-orchestrator`
  - Metadata detail (click row): JSONB content including products, quadrigrammes, `-R` flag, AI flag

### 2. CampaignCalendar

- Route: `https://liascan.tech/#/analysis/calendar`
- Component: `sigma-react-frontend/src/components/analysis/CampaignCalendar.tsx`
- The row's `start_date` = campaign_date surfaces an entry on that date cell.

### 3. LogManager

- Route: `https://liascan.tech/#/admin/logs`
- Component: `sigma-react-frontend/src/components/administration/LogManager.tsx`
- Filter: `component = CAMPAIGN_ORCHESTRATOR` and `details LIKE %{slug}%`
- The user sees the full phase timeline:
  - `INIT_DONE`, `CAMPAIGN_REGISTERED`
  - `COLLECTION_START` / `COLLECTION_DONE` (one pair per product)
  - `ANALYSIS_START` / `ANALYSIS_DONE` (one pair per quad)
  - `MERGE_START` / `MERGE_DONE`
  - `REPORTING_START` / `REPORTING_DONE`
  - `CAMPAIGN_COMPLETED`

## Polling pattern (React existing)

The existing CampaignManager already polls. No code change required in v1. The pattern (for reference):

```tsx
// Pattern used in ReportGenerationProgress.tsx
useEffect(() => {
  if (!campaignId) return;
  const pollStatus = async () => {
    const resp = await fetchWithConfig(`/api/campaigns/batch/${campaignId}/status`);
    setStatus(resp.data.status);
    setProgress(resp.data.progress);
    if (resp.data.status === 'completed' || resp.data.status === 'failed') {
      clearInterval(intervalRef.current);
    }
  };
  intervalRef.current = setInterval(pollStatus, 2000);
  return () => clearInterval(intervalRef.current);
}, [campaignId]);
```

If a `GET /api/campaigns/batch/{id}/status` endpoint is not already backed by `grc_campaigns`, the orchestrator's v1 run still surfaces in CampaignManager via the direct `grc_campaigns` table read. The developer should check the actual endpoint wiring and default to a direct SELECT if needed.

## RETEX console deeplinks (MANDATORY in Phase 7)

At COMPLETE, the orchestrator prints the three URLs, clickable in most terminals:

```
[RETEX] Campaign orchestrator: co-20260419-103000-adds-linx-pgsq

  CampaignManager :  https://liascan.tech/#/grc/campaigns
                     (Filter by name: "Orchestrated campaign co-20260419-...")

  CampaignCalendar:  https://liascan.tech/#/analysis/calendar
                     (Date: 2026-04-19)

  LogManager      :  https://liascan.tech/#/admin/logs?component=CAMPAIGN_ORCHESTRATOR&session_slug=co-20260419-103000-adds-linx-pgsq

  PPTX report     :  _alire/temp/campaign-orchestrator/co-20260419-.../reports/ADDS_20260419.pptx
  JSON report     :  _alire/temp/campaign-orchestrator/co-20260419-.../reports/ADDS_20260419.json
```

Replace `https://liascan.tech` with the local VPS root (`http://localhost:3000`) when running in dev on the VPS itself.

## v2 (optional): dedicated dashboard

When the user explicitly asks for a unified real-time dashboard, delegate creation to `/apex` + `/react-expert`. The component should:

- Name: `CampaignOrchestrationDashboard.tsx`
- Location: `sigma-react-frontend/src/components/grc/`
- Inputs: `session_slug` query param
- Data sources:
  - `GET /api/campaigns/batch/{grc_campaign_id}/status` (or a new `/api/campaigns/workflow/{session_slug}` endpoint via `/api-designer` + `/golang-pro`)
  - `GET /api/logs?component=CAMPAIGN_ORCHESTRATOR&session_slug={slug}` (via `LogManager` filter)
- UI:
  - MUI v7 `<Stepper>` with 4 steps (Collection, Analysis, Merge, Reporting)
  - `<LinearProgress>` per phase + per product
  - `<Timeline>` of `unified_logs` entries
  - Deeplinks to the PPTX and JSON files

R17 contract gate applies: fixture, render-and-assert, Playwright smoke test before merge.

## UI Help (R8)

When v2 dashboard is created, invoke `/create-ui-help` to add an entry for `campaign_orchestration_dashboard` in `ui_help_content`. Content must be English (R8). Skip this step in v1 (no new UI).

## Summary -- what "visible in UX" means for v1

| Signal | Visible where | Update frequency |
|--------|---------------|-------------------|
| Campaign exists | CampaignManager row | Immediate after Phase 1 |
| Status `running` | CampaignManager chip | Immediate at Phase 2 start |
| Progress 0-100 | CampaignManager progress bar | Per phase transition (2s polling) |
| Status `completed` | CampaignManager chip + `end_date` | Phase 5 end |
| Phase timeline | LogManager (filter) | Real-time (written on each LogSystemEvent) |
| Final reports | Filesystem path in RETEX console | End of run |

No new React component is required for v1. Every phase is surfaced via existing components backed by tables the orchestrator already writes to.
