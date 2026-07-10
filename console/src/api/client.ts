/**
 * Typed fetch client for the inspect_ia_agents platform API.
 *
 * Base URL comes from the environment (R5: no hardcoded provider URLs in
 * business logic; the localhost value is only a dev fallback).
 * All responses are raw JSON: there is no { success, data } envelope,
 * so nothing is unwrapped here.
 */

import type {
  ActionOutcome,
  ActionSpec,
  AgentAction,
  AgentConfig,
  AgentRegistry,
  CatalogRustSummary,
  CatalogSummary,
  DetectScanResult,
  DetectSignatures,
  DiscoveryOverview,
  AiBackend,
  AiProviderInfo,
  AuditEvent,
  BackendTestResult,
  Campaign,
  CampaignTemplate,
  ChainReport,
  ContainmentState,
  ControlSummary,
  DryRunResult,
  MetricsSummary,
  ObservabilityTrace,
  ObservabilityTraceSummary,
  OrchestrationGraph,
  PendingApproval,
  PolicyDocument,
  ProxyDebugStatus,
  ProxyTraceResponse,
  RealtimeStatus,
  ReceiptsResponse,
  RecordingMeta,
  ResolveResult,
  RunEvent,
  RunHandle,
  RunInfo,
  RunSummary,
  RecetteCampaignDetail,
  RecetteCampaignSummary,
  RunVerdict,
  RunVerdictSubmission,
  ServerEntry,
  ServerLifecycleResult,
  ServerLogTail,
  ServerStatus,
  ServerTestResult,
  VerdictJudgement,
  RagScorecard,
  VerdictScorecard,
  ProxyRouteState,
  ExchangeReport,
  ReconcileReport,
  ReconcileStatus,
  SessionsDeltaResponse,
  VerdictSubmission,
  VerdictSubmissionRequest,
  WireFlowResponse,
  WireStatus,
} from "../types/platform";

// Dev-only fallback when VITE_INSPECT_IA_AGENTS_API_URL is unset; recette.sh always
// sets it to the live API. 8090 is the canonical governed-API port (cicd/lib/common.sh, R19).
const API_BASE_URL: string =
  import.meta.env.VITE_INSPECT_IA_AGENTS_API_URL ?? "http://localhost:8090";

/** WebSocket base derived from the API base (http -> ws, https -> wss). */
function wsBaseUrl(): string {
  return API_BASE_URL.replace(/^http/, "ws");
}

/** Request body for executing an action through the gateway. */
export interface ExecuteActionRequest {
  agent_id: string;
  target_system: string;
  action_type: string;
  resource?: string;
  payload?: Record<string, unknown>;
}

/** Query parameters accepted by the audit events endpoint. */
export interface AuditEventsParams {
  from_seq?: number;
  limit?: number;
  /** Keep only the LAST n filtered events (live-tail backfill). Mutually exclusive with limit. */
  tail?: number;
  kind?: string;
  agent_id?: string;
  target_system?: string;
  event_id?: string;
}

/** Error thrown when the API answers with a non-2xx status. */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, path: string, body: string) {
    super(`API request failed (${status}) on ${path}: ${body}`);
    this.name = "ApiError";
    this.status = status;
  }
}

// Exported for sibling API modules (assistClient.ts) so they share the same
// base URL, headers, and ApiError semantics without growing this file.
export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
  });
  if (!res.ok) {
    const body = await res.text();
    throw new ApiError(res.status, path, body);
  }
  const text = await res.text();
  if (text.length === 0) {
    // 204 No Content (e.g. DELETE endpoints) carries no body.
    return undefined as T;
  }
  return JSON.parse(text) as T;
}

function withQuery(path: string, params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) {
      search.set(key, String(value));
    }
  }
  const qs = search.toString();
  return qs.length > 0 ? `${path}?${qs}` : path;
}

// ---------------------------------------------------------------------------
// Agent configuration (/config/*)
// ---------------------------------------------------------------------------

export function listAgents(): Promise<AgentConfig[]> {
  return request<AgentConfig[]>("/config/agents", { method: "GET" });
}

export function createAgent(agent: AgentConfig): Promise<AgentConfig> {
  return request<AgentConfig>("/config/agents", {
    method: "POST",
    body: JSON.stringify(agent),
  });
}

export function updateAgent(id: string, agent: AgentConfig): Promise<AgentConfig> {
  return request<AgentConfig>(`/config/agents/${encodeURIComponent(id)}`, {
    method: "PUT",
    body: JSON.stringify(agent),
  });
}

export function deleteAgent(id: string): Promise<void> {
  return request<void>(`/config/agents/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

export function listAiBackends(): Promise<AiBackend[]> {
  return request<AiBackend[]>("/config/ai-backends", { method: "GET" });
}

export function listAiProviders(): Promise<AiProviderInfo[]> {
  // The provider catalog that drives the dropdown -- backend is the source of
  // truth, so a new provider needs no frontend edit.
  return request<AiProviderInfo[]>("/config/ai-providers", { method: "GET" });
}

export function listAgentActions(): Promise<AgentAction[]> {
  // Backend wraps the list: {actions, count}.
  return request<{ actions: AgentAction[]; count: number }>("/agent-actions", {
    method: "GET",
  }).then((r) => r.actions);
}

export function createAiBackend(backend: AiBackend): Promise<AiBackend> {
  return request<AiBackend>("/config/ai-backends", {
    method: "POST",
    body: JSON.stringify(backend),
  });
}

export function deleteAiBackend(id: string): Promise<void> {
  return request<void>(`/config/ai-backends/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

/** Store the per-backend API key (write-only, R8).
 *
 *  The key is SENT only: it is never read back from the API and never logged
 *  here. Resolves with {configured: true}; rejects on 404 (unknown id) or
 *  400 (empty/missing api_key). */
export function setBackendSecret(
  id: string,
  apiKey: string,
): Promise<{ configured: boolean }> {
  return request<{ configured: boolean }>(
    `/config/ai-backends/${encodeURIComponent(id)}/secret`,
    { method: "PUT", body: JSON.stringify({ api_key: apiKey }) },
  );
}

/** Remove the per-backend API key (R8). Resolves on 204; rejects on 404. */
export function deleteBackendSecret(id: string): Promise<void> {
  return request<void>(
    `/config/ai-backends/${encodeURIComponent(id)}/secret`,
    { method: "DELETE" },
  );
}

/** Test an AI backend. Without a prompt this is the connectivity probe (one
 *  word back); with a non-empty prompt the model answers it. Always resolves
 *  with the outcome (the endpoint answers 200 for both ok and failed calls);
 *  only an unknown id rejects (404). The key never transits here (R8). */
export function testAiBackend(
  id: string,
  prompt?: string,
): Promise<BackendTestResult> {
  const body = prompt !== undefined ? { prompt } : {};
  return request<BackendTestResult>(
    `/config/ai-backends/${encodeURIComponent(id)}/test`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

// ---------------------------------------------------------------------------
// Servers (/config/servers): target servers + mock_local lifecycle + log tail
// ---------------------------------------------------------------------------

export function listServers(): Promise<ServerEntry[]> {
  return request<ServerEntry[]>("/config/servers", { method: "GET" });
}

export function createServer(server: ServerEntry): Promise<ServerEntry> {
  return request<ServerEntry>("/config/servers", {
    method: "POST",
    body: JSON.stringify(server),
  });
}

export function updateServer(id: string, server: ServerEntry): Promise<ServerEntry> {
  return request<ServerEntry>(`/config/servers/${encodeURIComponent(id)}`, {
    method: "PUT",
    body: JSON.stringify(server),
  });
}

export function deleteServer(id: string): Promise<void> {
  return request<void>(`/config/servers/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

export function startServer(id: string): Promise<ServerLifecycleResult> {
  return request<ServerLifecycleResult>(
    `/config/servers/${encodeURIComponent(id)}/start`,
    { method: "POST", body: JSON.stringify({}) },
  );
}

export function stopServer(id: string): Promise<ServerLifecycleResult> {
  return request<ServerLifecycleResult>(
    `/config/servers/${encodeURIComponent(id)}/stop`,
    { method: "POST", body: JSON.stringify({}) },
  );
}

export function getServerStatus(id: string): Promise<{ status: ServerStatus }> {
  return request<{ status: ServerStatus }>(
    `/config/servers/${encodeURIComponent(id)}/status`,
    { method: "GET" },
  );
}

export function getServerLog(id: string, after = 0): Promise<ServerLogTail> {
  return request<ServerLogTail>(
    withQuery(`/config/servers/${encodeURIComponent(id)}/log`, { after }),
    { method: "GET" },
  );
}

/** Request body for POST /config/servers/{id}/test. */
export interface ServerTestRequest {
  action_type: string;
  resource?: string;
  payload?: Record<string, unknown>;
}

export function testServer(
  id: string,
  body: ServerTestRequest,
): Promise<ServerTestResult> {
  return request<ServerTestResult>(
    `/config/servers/${encodeURIComponent(id)}/test`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

/** Global private-DNS containment flag. Raw dict, no envelope to unwrap. */
export function getContainment(): Promise<ContainmentState> {
  return request<ContainmentState>("/config/containment", { method: "GET" });
}

export function setContainment(enabled: boolean): Promise<ContainmentState> {
  return request<ContainmentState>("/config/containment", {
    method: "PUT",
    body: JSON.stringify({ enabled }),
  });
}

/** Probe how a name resolves against the server allowlist (diagnostic, no
 *  side effect). A denied probe returns HTTP 200 with resolved=false, never a
 *  thrown error. When containment is omitted the backend uses its global flag.
 *  Raw dict, no envelope to unwrap. */
export function resolveName(
  name: string,
  containment?: boolean,
): Promise<ResolveResult> {
  const body: { name: string; containment?: boolean } = { name };
  if (containment !== undefined) {
    body.containment = containment;
  }
  return request<ResolveResult>("/config/resolve", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// ---------------------------------------------------------------------------
// Runs: launch / inspect / stop agents and recette runners
// ---------------------------------------------------------------------------

/** Body to launch a Lane B agent. Provide stub_script to run it as a mock,
 *  otherwise the agent's bound ai_backend_id drives a live LLM (key from env). */
export interface LaunchLaneBRequest {
  agent_id: string;
  stub_script?: Array<Record<string, unknown>>;
}

export function launchLaneB(req: LaunchLaneBRequest): Promise<RunHandle> {
  const params: Record<string, unknown> = { agent_id: req.agent_id };
  if (req.stub_script !== undefined) {
    params.stub_script = req.stub_script;
  }
  return request<RunHandle>("/runs", {
    method: "POST",
    body: JSON.stringify({ kind: "lane_b", params }),
  });
}

/** Launch an agent as a SEPARATE OS process (eBPF-observable, mock-only). The
 *  process-mode run is the prerequisite for a live eBPF capture of the agent
 *  (the in-process run is invisible to the kernel tracepoints). */
export function launchProcessRun(agentId: string): Promise<RunHandle> {
  return request<RunHandle>("/runs", {
    method: "POST",
    body: JSON.stringify({ kind: "lane_b_process", params: { agent_id: agentId } }),
  });
}

export function launchRunner(
  kind: "discovery" | "identification",
  params: Record<string, unknown> = {},
): Promise<RunHandle> {
  return request<RunHandle>("/runs", {
    method: "POST",
    body: JSON.stringify({ kind, params }),
  });
}

export function listRuns(): Promise<RunSummary[]> {
  return request<{ runs: RunSummary[] }>("/runs", { method: "GET" }).then(
    (r) => r.runs,
  );
}

export function getRun(runId: string): Promise<RunInfo> {
  return request<RunInfo>(`/runs/${encodeURIComponent(runId)}`, { method: "GET" });
}

/**
 * Purge finished runs from the ephemeral run read-model (optionally for one
 * agent). Active runs are preserved server-side; the append-only audit log is
 * never touched (I1). Returns the number of run records removed.
 */
export function purgeRuns(agentId?: string): Promise<{ removed: number }> {
  const path = agentId === undefined ? "/runs" : withQuery("/runs", { agent_id: agentId });
  return request<{ removed: number }>(path, { method: "DELETE" });
}

export function getRunVerdict(runId: string): Promise<RunVerdict> {
  return request<RunVerdict>(`/runs/${encodeURIComponent(runId)}/verdict`, {
    method: "GET",
  });
}

/**
 * Judge this run's real action log (F1) and push it onto the Verdicts board,
 * exactly as an external identification tool would (POST /verdicts). The
 * submission is judged against the agent's stored ground_truth server-side, so
 * an agent without ground truth yields a SKIP entry, never a vacuous PASS.
 */
export function submitRunVerdict(runId: string): Promise<RunVerdictSubmission> {
  return request<RunVerdictSubmission>(
    `/runs/${encodeURIComponent(runId)}/submit-verdict`,
    { method: "POST", body: JSON.stringify({}) },
  );
}

export function getRunEvents(runId: string): Promise<RunEvent[]> {
  return request<RunEvent[]>(`/runs/${encodeURIComponent(runId)}/events`, {
    method: "GET",
  });
}

export function stopRun(runId: string): Promise<{ stopped: boolean }> {
  return request<{ stopped: boolean }>(
    `/runs/${encodeURIComponent(runId)}/stop`,
    { method: "POST", body: JSON.stringify({}) },
  );
}

/** Open the live event WebSocket for a run. Caller owns close(). */
export function openRunSocket(runId: string): WebSocket {
  return new WebSocket(`${wsBaseUrl()}/runs/${encodeURIComponent(runId)}/ws`);
}

// ---------------------------------------------------------------------------
// Campaigns + replayable recordings
// ---------------------------------------------------------------------------

export function listCampaigns(): Promise<Campaign[]> {
  return request<{ campaigns: Campaign[] }>("/campaigns", { method: "GET" }).then(
    (r) => r.campaigns,
  );
}

/** Read-only recette governance campaigns (campaigns/**); distinct from the
 *  CRUD campaigns above. Listing + explain only -- never run from here. */
export function listRecetteCampaigns(): Promise<RecetteCampaignSummary[]> {
  return request<{ campaigns: RecetteCampaignSummary[] }>("/recette-campaigns", {
    method: "GET",
  }).then((r) => r.campaigns);
}

export function getRecetteCampaign(id: string): Promise<RecetteCampaignDetail> {
  return request<RecetteCampaignDetail>(`/recette-campaigns/${encodeURIComponent(id)}`, {
    method: "GET",
  });
}

export function createCampaign(campaign: Campaign): Promise<Campaign> {
  return request<Campaign>("/campaigns", {
    method: "POST",
    body: JSON.stringify(campaign),
  });
}

export function deleteCampaign(id: string): Promise<void> {
  return request<void>(`/campaigns/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export function listCampaignTemplates(): Promise<CampaignTemplate[]> {
  return request<{ templates: CampaignTemplate[] }>("/campaign-templates", {
    method: "GET",
  }).then((r) => r.templates);
}

export function instantiateTemplate(id: string): Promise<Campaign> {
  return request<Campaign>(
    `/campaign-templates/${encodeURIComponent(id)}/instantiate`,
    { method: "POST", body: JSON.stringify({}) },
  );
}

export function runCampaign(id: string): Promise<RunHandle> {
  return request<RunHandle>(`/campaigns/${encodeURIComponent(id)}/run`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export function listRecordings(): Promise<RecordingMeta[]> {
  return request<{ recordings: RecordingMeta[] }>("/recordings", {
    method: "GET",
  }).then((r) => r.recordings);
}

/** Replay a recording (deterministic, I4). `paceMs` > 0 slows the step-frame
 *  emission for slow-motion review; the replayed action log is identical at
 *  any speed (pacing is operational, never a decision input). */
export function replayRecording(recordingId: string, paceMs = 0): Promise<RunHandle> {
  return request<RunHandle>(
    `/recordings/${encodeURIComponent(recordingId)}/replay?pace_ms=${encodeURIComponent(paceMs)}`,
    { method: "POST", body: JSON.stringify({}) },
  );
}

// ---------------------------------------------------------------------------
// Action catalog and execution
// ---------------------------------------------------------------------------

export function getCatalog(targetSystem?: string): Promise<ActionSpec[]> {
  // Backend wraps the list: {actions: [...], count: N}.
  return request<{ actions: ActionSpec[]; count: number }>(
    withQuery("/catalog/actions", { target_system: targetSystem }),
    { method: "GET" },
  ).then((res) => res.actions);
}

export function executeAction(req: ExecuteActionRequest): Promise<ActionOutcome> {
  return request<ActionOutcome>("/actions/execute", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

// ---------------------------------------------------------------------------
// Agent catalog registry (/catalog/summary): the discovery catalog view
// ---------------------------------------------------------------------------

/**
 * GET /catalog/summary: the registry of published agents plus aggregate counts.
 *
 * The endpoint answers with the raw catalog object (like the other routes in
 * this API), so callers receive the bare CatalogSummary directly -- there is no
 * { success, data } envelope to unwrap.
 */
export function getCatalogSummary(): Promise<CatalogSummary> {
  return request<CatalogSummary>("/catalog/summary", { method: "GET" });
}

/**
 * GET /catalog/rust-summary: run the native Rust discovery engine
 * (discoveryprobe-catalog) on the same registry and return its invariant
 * summary plus whether it agrees with the Python projection. Raw object, no
 * envelope. `available: false` when the binary is not built (fail-safe).
 */
export function getCatalogRustSummary(): Promise<CatalogRustSummary> {
  return request<CatalogRustSummary>("/catalog/rust-summary", { method: "GET" });
}

// ---------------------------------------------------------------------------
// Reperage (/detect/*): observability-tool detection
// ---------------------------------------------------------------------------

/**
 * GET /detect/signatures: the catalog of detectable observability tools (each
 * with its category and the literal needles that betray it) plus the sorted
 * union of categories.
 *
 * The endpoint answers with the raw object (like the other routes in this API),
 * so callers receive the bare DetectSignatures directly -- there is no
 * { success, data } envelope to unwrap.
 */
export function getDetectSignatures(): Promise<DetectSignatures> {
  return request<DetectSignatures>("/detect/signatures", { method: "GET" });
}

/**
 * POST /detect/scan: scan a free-form text for observability-tool needles.
 * Resolves with the raw match list (no envelope to unwrap); an empty
 * `matches` array means no tool was detected.
 */
export function scanForObservability(text: string): Promise<DetectScanResult> {
  return request<DetectScanResult>("/detect/scan", {
    method: "POST",
    body: JSON.stringify({ text }),
  });
}

// ---------------------------------------------------------------------------
// Discovery overview (/discovery/overview): the unified operator dashboard
// ---------------------------------------------------------------------------

/**
 * GET /discovery/overview: the unified catalog + reperage tally driving the
 * Discovery dashboard. The endpoint answers with the raw object (like the other
 * routes in this API), so callers receive the bare DiscoveryOverview directly --
 * there is no { success, data } envelope to unwrap.
 */
export function getDiscoveryOverview(): Promise<DiscoveryOverview> {
  return request<DiscoveryOverview>("/discovery/overview", { method: "GET" });
}

// ---------------------------------------------------------------------------
// Approvals (I6: pending actions block until resolved or timed out)
// ---------------------------------------------------------------------------

export function listPendingApprovals(): Promise<PendingApproval[]> {
  // Backend wraps the list: {pending: [...]}.
  return request<{ pending: PendingApproval[] }>("/approvals?state=pending", {
    method: "GET",
  }).then((res) => res.pending);
}

export function approveAction(
  eventId: string,
  approver: string,
  reason?: string,
): Promise<ActionOutcome> {
  return request<ActionOutcome>(
    `/approvals/${encodeURIComponent(eventId)}/approve`,
    { method: "POST", body: JSON.stringify({ approver, reason }) },
  );
}

export function denyAction(
  eventId: string,
  approver: string,
  reason?: string,
): Promise<ActionOutcome> {
  return request<ActionOutcome>(
    `/approvals/${encodeURIComponent(eventId)}/deny`,
    { method: "POST", body: JSON.stringify({ approver, reason }) },
  );
}

export interface SweepResult {
  timed_out: string[];
}

export function sweepTimeouts(): Promise<SweepResult> {
  return request<SweepResult>("/approvals/sweep-timeouts", {
    method: "POST",
    body: JSON.stringify({}),
  });
}

// ---------------------------------------------------------------------------
// Audit plane (append-only event store, I1)
// ---------------------------------------------------------------------------

export function listAuditEvents(params: AuditEventsParams = {}): Promise<AuditEvent[]> {
  // Backend wraps the list: {events: [...]}.
  return request<{ events: AuditEvent[] }>(
    withQuery("/audit/events", {
      from_seq: params.from_seq,
      limit: params.limit,
      tail: params.tail,
      kind: params.kind,
      agent_id: params.agent_id,
      target_system: params.target_system,
      event_id: params.event_id,
    }),
    { method: "GET" },
  ).then((res) => res.events);
}

export function verifyChain(): Promise<ChainReport> {
  return request<ChainReport>("/audit/verify", { method: "GET" });
}

// ---------------------------------------------------------------------------
// Side-effect proxy debug traces (I5 observability, read-only)
// ---------------------------------------------------------------------------

/** Recorded side-effect traces (oldest first). tail keeps only the last N;
 *  runId narrows the view to one run (F3 run <-> traces link). */
export function getProxyTraces(
  tail?: number,
  runId?: string,
): Promise<ProxyTraceResponse> {
  return request<ProxyTraceResponse>(
    withQuery("/proxy/traces", { tail, run_id: runId }),
    { method: "GET" },
  );
}

/** Server-side selection for the /proxy/traces delta poll. All optional;
 *  camelCase here, mapped to the snake_case query params by the client. */
export interface ProxyTracesQuery {
  /** Compat: keep only the last N (wins over limit, ignores sinceSeq). */
  tail?: number;
  runId?: string;
  /** Delta cursor: only rows with seq > sinceSeq. Feed back `last_seq`. */
  sinceSeq?: number;
  agentId?: string;
  target?: string;
  outcome?: "ok" | "fail";
  /** Literal substring filter (SQL-side). */
  q?: string;
  /** Keep the first N of the ascending delta. */
  limit?: number;
}

/** Delta-poll of the recorded side-effect traces (oldest first). Send the
 *  previous `last_seq` as sinceSeq to fetch only new rows; when the response
 *  flags `reset` (server buffer cleared/restarted, cursor ahead) it already
 *  carries the full current selection -- replace, do not append. */
export function getProxyTracesDelta(params: ProxyTracesQuery): Promise<ProxyTraceResponse> {
  return request<ProxyTraceResponse>(
    withQuery("/proxy/traces", {
      tail: params.tail,
      run_id: params.runId,
      since_seq: params.sinceSeq,
      agent_id: params.agentId,
      target: params.target,
      outcome: params.outcome,
      q: params.q,
      limit: params.limit,
    }),
    { method: "GET" },
  );
}

/** Debug toggle state plus the buffered trace count. */
export function getProxyDebugStatus(): Promise<ProxyDebugStatus> {
  return request<ProxyDebugStatus>("/proxy/debug", { method: "GET" });
}

/** Toggle side-effect trace recording at runtime (operator action). */
export function setProxyDebug(enabled: boolean): Promise<{ debug_enabled: boolean }> {
  return request<{ debug_enabled: boolean }>("/proxy/debug", {
    method: "POST",
    body: JSON.stringify({ enabled }),
  });
}

/** Discard the debug trace buffer (the append-only audit log is untouched, I1). */
export function clearProxyTraces(): Promise<{ cleared: boolean }> {
  return request<{ cleared: boolean }>("/proxy/traces", { method: "DELETE" });
}

// ---------------------------------------------------------------------------
// Wire overlay (optional mitmproxy interception, network-level I5 view)
// ---------------------------------------------------------------------------

/** Intercepted wire flows (oldest first). tail keeps the last N; runId narrows
 *  to one run. Empty (and enabled=false) when the overlay is not configured. */
export function getWireFlows(tail?: number, runId?: string): Promise<WireFlowResponse> {
  return request<WireFlowResponse>(withQuery("/proxy/wire", { tail, run_id: runId }), {
    method: "GET",
  });
}

/** Server-side selection for the /proxy/wire delta poll. All optional;
 *  camelCase here, mapped to the snake_case query params by the client. */
export interface WireFlowsQuery {
  /** Compat: keep only the last N (wins over limit, ignores sinceSeq). */
  tail?: number;
  runId?: string;
  /** Delta cursor: only rows with seq > sinceSeq. Feed back `last_seq`. */
  sinceSeq?: number;
  host?: string;
  /** Matched case-insensitively (the store uppercases before comparing). */
  method?: string;
  /** Exact status_code match. */
  status?: number;
  /** Literal substring filter over path and bodies (SQL-side). */
  q?: string;
  /** Keep the first N of the ascending delta. */
  limit?: number;
}

/** Delta-poll of the intercepted wire flows (oldest first). Send the previous
 *  `last_seq` as sinceSeq to fetch only new rows; when the response flags
 *  `reset` (server buffer cleared/restarted, cursor ahead) it already carries
 *  the full current selection -- replace, do not append. */
export function getWireFlowsDelta(params: WireFlowsQuery): Promise<WireFlowResponse> {
  return request<WireFlowResponse>(
    withQuery("/proxy/wire", {
      tail: params.tail,
      run_id: params.runId,
      since_seq: params.sinceSeq,
      host: params.host,
      method: params.method,
      status: params.status,
      q: params.q,
      limit: params.limit,
    }),
    { method: "GET" },
  );
}

/** Overlay state (configured?) plus its proxy URL and buffered flow count. */
export function getWireStatus(): Promise<WireStatus> {
  return request<WireStatus>("/proxy/wire/status", { method: "GET" });
}

/** Start/stop the optional mitmproxy wire overlay (operator action, guarded). */
export function controlWireOverlay(
  action: "up" | "down",
): Promise<{ ok: boolean; action: string; returncode: number; next_step: string | null }> {
  return request("/proxy/wire/overlay", {
    method: "POST",
    body: JSON.stringify({ action }),
  });
}

/** Discard the wire flow buffer (the append-only audit log is untouched, I1). */
export function clearWireFlows(): Promise<{ cleared: boolean }> {
  return request<{ cleared: boolean }>("/proxy/wire", { method: "DELETE" });
}

/** Wire<->audit reconciliation: ok=false when a wire flow reached a non-mediated
 *  target (no matching audit event). runId narrows the join to one run. strict
 *  selects the phase-3 per-flow side_effect_hash join (catches a ghost hitting an
 *  allowlisted target directly). */
export function getReconcile(runId?: string, strict?: boolean): Promise<ReconcileReport> {
  return request<ReconcileReport>(
    withQuery("/proxy/reconcile", { run_id: runId, strict: strict ? "true" : undefined }),
    { method: "GET" },
  );
}

/** Lightweight reconciliation verdict (ok + bypass_count, no flows) for the
 *  source-menu badge -- the same join as getReconcile without the full payload,
 *  pollable without the reconcile panel being open. */
export function getReconcileStatus(
  runId?: string,
  strict?: boolean,
): Promise<ReconcileStatus> {
  return request<ReconcileStatus>(
    withQuery("/proxy/reconcile/status", {
      run_id: runId,
      strict: strict ? "true" : undefined,
    }),
    { method: "GET" },
  );
}

/** Parameters of the coalesced /proxy/sessions/delta poll. Cursors are
 *  independent per side: sinceSeq for traces, wireSinceSeq for wire flows. */
export interface SessionsDeltaQuery {
  /** Trace delta cursor. Feed back the response's `last_seq`. */
  sinceSeq?: number;
  /** Wire delta cursor. Feed back the response's `wire_last_seq`. */
  wireSinceSeq?: number;
  /** Scopes the WIRE delta and the reconcile join only (traces stay unfiltered,
   *  mirroring the SessionsPanel's client-side grouping). */
  runId?: string;
  /** Backend default true (strict per-flow hash join); false relaxes it. */
  strict?: boolean;
}

/** Coalesced SessionsPanel poll: traces + wire + reconcile in ONE round trip
 *  (replaces three parallel requests per tick). Each side has its own delta
 *  cursor and its own reset flag with the usual contract: a `reset`/
 *  `wire_reset` response already carries the full current selection for that
 *  side -- replace, do not append; a stale cursor on one side never forces a
 *  resync of the other. */
export function getProxySessionsDelta(
  params: SessionsDeltaQuery = {},
): Promise<SessionsDeltaResponse> {
  return request<SessionsDeltaResponse>(
    withQuery("/proxy/sessions/delta", {
      since_seq: params.sinceSeq,
      wire_since_seq: params.wireSinceSeq,
      run_id: params.runId,
      // Backend defaults to strict=true; only an explicit opt-out is sent.
      strict: params.strict === false ? "false" : undefined,
    }),
    { method: "GET" },
  );
}

/** Discovery verdict overlaid on the real exchange (GET /proxy/discovery-exchange).
 *  Per-agent hook detection + per-exchange identified/ghost verdict, scored by the
 *  deterministic surface oracle (the always-available default source; the eBPF
 *  source is captureProbe). runId narrows to one run; strict (default true) uses
 *  the phase-3 per-flow side_effect_hash join for the ghost-exchange annotation. */
export function getDiscoveryExchange(runId?: string, strict = true): Promise<ExchangeReport> {
  return request<ExchangeReport>(
    withQuery("/proxy/discovery-exchange", {
      run_id: runId,
      strict: strict ? undefined : "false",
    }),
    { method: "GET" },
  );
}

/** Record each detected bypass as a compensatory bypass_detected event in the
 *  append-only audit log (I1). Idempotent: a bypass already recorded is not
 *  appended twice. Returns how many NEW events were raised. strict raises the
 *  phase-3 detections too. */
export function raiseReconcile(
  runId?: string,
  strict?: boolean,
): Promise<{ raised: number; event_ids: string[] }> {
  return request<{ raised: number; event_ids: string[] }>(
    withQuery("/proxy/reconcile/raise", { run_id: runId, strict: strict ? "true" : undefined }),
    { method: "POST" },
  );
}

/** The selectable transport targets (direct vs wire overlay) + the active one. */
export function getProxyRoute(): Promise<ProxyRouteState> {
  return request<ProxyRouteState>("/proxy/route", { method: "GET" });
}

/** Select the active transport target; applies to runs started afterwards. */
export function setProxyRoute(target: string): Promise<{ active: string; proxy_url: string | null }> {
  return request<{ active: string; proxy_url: string | null }>("/proxy/route", {
    method: "POST",
    body: JSON.stringify({ target }),
  });
}

/**
 * Absolute URL of the realtime SSE stream (G4). The console opens this with an
 * EventSource; it carries a derived live tail of governed events, never the
 * source of truth (I1) -- history is backfilled from the audit endpoints.
 */
export function realtimeStreamUrl(): string {
  return `${API_BASE_URL}/events/stream`;
}

/**
 * Absolute URL of the wire live-capture SSE stream. Data-light wake-up channel:
 * `cursor` events carry only the buffer's last_seq; the panel re-fetches via
 * the delta endpoint (single data path, cursor-consistent).
 */
export function wireStreamUrl(): string {
  return `${API_BASE_URL}/proxy/wire/stream`;
}

/** Realtime transport health for the live-feed badge. */
export function getRealtimeStatus(): Promise<RealtimeStatus> {
  return request<RealtimeStatus>("/events/status", { method: "GET" });
}

// ---------------------------------------------------------------------------
// Verdicts: external tool results judged against stored ground truth
// ---------------------------------------------------------------------------

/** Resolve to null when the expected-absent case answers 404 (no submission yet). */
async function nullOn404<T>(promise: Promise<T>): Promise<T | null> {
  try {
    return await promise;
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      return null;
    }
    throw err;
  }
}

/** Latest judged submission, or null when no tool has submitted yet (404). */
export function getVerdicts(): Promise<VerdictSubmission | null> {
  return nullOn404(request<VerdictSubmission>("/verdicts", { method: "GET" }));
}

/** Aggregates over the latest submission, or null when none exists (404). */
export function getVerdictScorecard(): Promise<VerdictScorecard | null> {
  return nullOn404(request<VerdictScorecard>("/verdicts/scorecard", { method: "GET" }));
}

/** Every judged submission, oldest-first (empty list when none). */
export function getVerdictHistory(): Promise<VerdictSubmission[]> {
  return request<VerdictSubmission[]>("/verdicts/history", { method: "GET" });
}

/** Submit tool results; the API judges them against each agent's ground truth. */
export function postVerdicts(body: VerdictSubmissionRequest): Promise<VerdictJudgement> {
  return request<VerdictJudgement>("/verdicts", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// ---------------------------------------------------------------------------
// Policies (versioned, I4: decisions record the policy version applied)
// ---------------------------------------------------------------------------

export interface PolicyListing {
  versions: string[];
  active: string | null;
}

export function listPolicies(): Promise<PolicyListing> {
  return request<PolicyListing>("/policies", { method: "GET" });
}

export function getActivePolicy(): Promise<PolicyDocument> {
  return request<PolicyDocument>("/policies/active", { method: "GET" });
}

export function publishPolicy(doc: PolicyDocument): Promise<PolicyDocument> {
  return request<PolicyDocument>("/policies", {
    method: "POST",
    body: JSON.stringify(doc),
  });
}

export function setActivePolicy(version: string): Promise<PolicyDocument> {
  return request<PolicyDocument>("/policies/active", {
    method: "PUT",
    body: JSON.stringify({ version }),
  });
}

// ---------------------------------------------------------------------------
// RAG retrieval-quality recette (/rag/*)
// ---------------------------------------------------------------------------

/** GET /rag/scorecard: the deterministic retrieval recette result (raw JSON). */
export function getRagScorecard(): Promise<RagScorecard> {
  return request<RagScorecard>("/rag/scorecard");
}

/** One knowledge-base document as listed by the operator CRUD. */
export interface KbDocument {
  id: string;
  title: string;
  tags: string[];
  poisoned: boolean;
  threat: string | null;
}

/** A document insertion payload (operator path, off the agent path). */
export interface KbDocumentInput {
  id: string;
  title: string;
  content: string;
  poisoned: boolean;
  tags: string[];
}

/** GET /rag/documents: the current knowledge base (baseline + applied scenario). */
export function listKbDocuments(): Promise<KbDocument[]> {
  return request<{ documents: KbDocument[] }>("/rag/documents").then((r) => r.documents);
}

/** POST /rag/documents: insert a document (operator, off the agent path). */
export function addKbDocument(doc: KbDocumentInput): Promise<KbDocument> {
  return request<KbDocument>("/rag/documents", {
    method: "POST",
    body: JSON.stringify(doc),
  });
}

/** DELETE /rag/documents/{id}. */
export function deleteKbDocument(id: string): Promise<void> {
  return request<void>(`/rag/documents/${encodeURIComponent(id)}`, { method: "DELETE" });
}

/** POST /rag/reset: restore the clean baseline (un-poison). */
export function resetKb(): Promise<{ reset: boolean; documents: number }> {
  return request<{ reset: boolean; documents: number }>("/rag/reset", { method: "POST" });
}

/** GET /rag/scenarios: the named poison scenarios. */
export function listRagScenarios(): Promise<string[]> {
  return request<{ scenarios: string[] }>("/rag/scenarios").then((r) => r.scenarios);
}

/** POST /rag/scenario/{name}/apply: inject a named scenario's documents. */
export function applyRagScenario(name: string): Promise<{ applied: string; injected: string[] }> {
  return request<{ applied: string; injected: string[] }>(
    `/rag/scenario/${encodeURIComponent(name)}/apply`,
    { method: "POST" },
  );
}

// ---------------------------------------------------------------------------
// Unified recette scorecard (/subjects/scorecard)
// ---------------------------------------------------------------------------

export interface DiscoverySurfaceScore {
  repos: number;
  passed: number;
  false_positives: number;
  false_negatives: number;
  ordering_ok: boolean;
  all_passed: boolean;
}

export interface IdentificationScore {
  agents: number;
  passed: number;
  false_positives: number;
  false_negatives: number;
  all_passed: boolean;
}

export interface OrchestrationScore {
  teams: number;
  passed: number;
  false_positives: number;
  false_negatives: number;
  all_passed: boolean;
}

export interface RecetteScorecard {
  identification: IdentificationScore;
  maf: IdentificationScore;
  orchestration: OrchestrationScore;
  discovery: Record<string, DiscoverySurfaceScore>;
  all_passed: boolean;
}

/** GET /subjects/scorecard: aggregate recette verdict over the unified corpus
 *  (identification + MAF + every discovery surface, including mcp). Raw JSON. */
export function getRecetteScorecard(): Promise<RecetteScorecard> {
  return request<RecetteScorecard>("/subjects/scorecard");
}

/** One repo's discovery verdict: detected vs expected, pass/fail, and the
 *  human-readable failure reasons (empty when it passed). */
export interface DiscoveryRepoDetail {
  repo: string;
  detected: boolean;
  expected: boolean;
  passed: boolean;
  false_positive: boolean;
  false_negative: boolean;
  detail: string[];
}

/** GET /discovery/check: the per-repo discovery detail behind the aggregate. */
export interface DiscoveryCheck {
  all_passed: boolean;
  total: number;
  passed: number;
  detection_rate: number;
  false_positives: number;
  false_negatives: number;
  ordering_ok: boolean;
  repos: DiscoveryRepoDetail[];
}

/** GET /discovery/check: the drill-down behind the discovery scorecard -- every
 *  repo with its detected/expected verdict and failure reasons. Raw JSON. */
export function getDiscoveryCheck(): Promise<DiscoveryCheck> {
  return request<DiscoveryCheck>("/discovery/check");
}

// ---------------------------------------------------------------------------
// Probe (/probe/*): the discoveryprobe eBPF reference capture (design 12.5/12.6)
// ---------------------------------------------------------------------------

/** One agent's capture: the identifiers visible on each observation surface. */
export interface SurfaceRecording {
  agent_id: string;
  surfaces: Record<string, string[]>;
}

/** The broker reply: ok with recordings, or rejected with a reason. `mode`
 *  ("replay" | "live") tags how the recording was produced. */
export interface BrokerRecording {
  status: string;
  recordings?: SurfaceRecording[];
  recording_sha256?: string;
  reason?: string;
  mode?: string;
}

/** The source-agnostic detection scorecard (recette/surface). */
export interface DetectionScorecard {
  ok: boolean;
  total_agents: number;
  detected_per_surface: Record<string, number>;
  false_negatives: string[];
}

/** One live sighting from the passive eBPF monitor: an agent seen on the wire. */
export interface ProbeSighting {
  agent_id: string;
  surfaces: string[];
  windows_seen: number;
  last_window: number;
}

/** GET /probe/monitor: the passive watch state + rolling live sightings. */
export interface ProbeMonitorState {
  running: boolean;
  window_ms: number;
  agents: string[];
  windows: number;
  last_error: string | null;
  sightings: ProbeSighting[];
}

/** Live state of the passive eBPF watch (agents seen on the wire in ~real time). */
export function getProbeMonitor(): Promise<ProbeMonitorState> {
  return request<ProbeMonitorState>("/probe/monitor");
}

/** Start the passive watch (agents default to all configured ids). */
export function startProbeMonitor(
  agents?: string[],
  windowMs?: number,
): Promise<{ started: boolean; mode: string; agents: string[] }> {
  return request("/probe/monitor/start", {
    method: "POST",
    body: JSON.stringify({ agents, window_ms: windowMs }),
  });
}

/** Stop the passive watch (idempotent). */
export function stopProbeMonitor(): Promise<{ running: boolean }> {
  return request("/probe/monitor/stop", { method: "POST" });
}

/** Spawn an agent as its own process and capture it by PID (precise eBPF): the
 *  broker attributes by the spawned child's exact pid, not the 15-byte comm. */
export function processCapture(
  agentId: string,
  durationMs?: number,
): Promise<ProbeCaptureResult> {
  return request<ProbeCaptureResult>("/probe/process-capture", {
    method: "POST",
    body: JSON.stringify({ agent_id: agentId, duration_ms: durationMs }),
  });
}

/** One annotated endpoint from the v1 named-wire capture result. */
export interface WireEndpoint {
  raw: string;
  name: string | null;
  undeclared: boolean;
}

/** POST /probe/capture result: the broker recording + (when ok) its scorecard. */
/** One logging recommendation the discovery emits for an agent: what to log + why,
 *  tiered alert | warn | info. */
export interface LoggingRecommendation {
  severity: "alert" | "warn" | "info";
  log: string;
  why: string;
}

/** The discovery's per-agent analysis (its job): PLANNED (declared) vs SAID
 *  (decided) vs DONE (kernel-seen) coherence + what to log. */
export interface AgentAnalysis {
  agent_id: string;
  identified: boolean;
  seen_kinds: string[];
  planned: { systems: string[]; scope: string[] };
  said: { actions: string[] } | null;
  done: {
    dialed_servers: string[];
    undeclared_egress: string[];
    undeclared_dns: string[];
    process_spawned: boolean;
    sensitive_opens: string[];
    credential_opens: string[];
    doh_egress: string[];
  };
  coherent: boolean;
  logging_recommendations: LoggingRecommendation[];
  analysis: string;
}

export interface ProbeCaptureResult {
  recording: BrokerRecording;
  scorecard?: DetectionScorecard;
  wire_named?: Record<string, WireEndpoint[]>;
  undeclared_hosts?: string[];
  undeclared_dns?: string[];
  agent_analysis?: AgentAnalysis[];
}

/** POST /probe/process-capture-campaign result: every mock-capable step spawned
 *  as a process and captured by PID in one window. `agents` were captured,
 *  `skipped` could not run mock (real / no scenario -- never faked). */
export interface ProbeCampaignCaptureResult extends ProbeCaptureResult {
  agents: string[];
  skipped: Array<{ agent_id: string; reason: string }>;
}

/** Spawn every step of a campaign as its own process and capture them by PID in
 *  one eBPF window (the campaign analogue of processCapture). Mock-only. */
export function processCaptureCampaign(
  campaignId: string,
  durationMs?: number,
): Promise<ProbeCampaignCaptureResult> {
  return request<ProbeCampaignCaptureResult>("/probe/process-capture-campaign", {
    method: "POST",
    body: JSON.stringify({ campaign_id: campaignId, duration_ms: durationMs }),
  });
}

/** GET /probe/status: whether the broker socket is configured. `mode` is
 *  "replay" (deterministic replay of corpus surface ground-truth, no CAP_BPF),
 *  "live" (privileged eBPF broker) or "off" (no broker). Surfaced so the console
 *  never presents a replay as a live eBPF capture. */
export interface ProbeStatus {
  configured: boolean;
  socket_env: string;
  mode: "replay" | "live" | "off";
}

export interface ProbeCaptureRequest {
  agents: string[];
  duration_ms?: number;
}

/** GET /probe/status: is the capture broker reachable for the UI to enable capture? */
export function getProbeStatus(): Promise<ProbeStatus> {
  return request<ProbeStatus>("/probe/status");
}

/** POST /probe/capture: relay a bounded eBPF capture to the broker and get the
 *  recording + detection scorecard. The API is non-privileged; the broker holds
 *  CAP_BPF. A 503 means the broker is not launched / unreachable (fail-safe). */
export function captureProbe(req: ProbeCaptureRequest): Promise<ProbeCaptureResult> {
  return request<ProbeCaptureResult>("/probe/capture", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

// --- Agent inventory (GET /probe/inventory) ---

/** One communication edge in the inventory comm graph (agent -> agent). */
export interface InventoryEdge {
  from: string;
  to: string;
}

/** Kind-tagged passport situation of a scanned agent. Present carries the parsed
 *  passport, absent the code evidence, invalid the parse/validation errors. */
export type InventoryPassport =
  | { kind: "present"; passport: unknown }
  | { kind: "absent"; evidence: string[] }
  | { kind: "invalid"; errors: string[] };

/** Kind-tagged conformity verdict; only `violations` carries a list. */
export type InventoryConformity =
  | { kind: "conform" }
  | { kind: "not_observed" }
  | { kind: "violations"; violations: InventoryViolation[] };

/** Kind-tagged violation. Only the fields for a given `kind` are present. */
export interface InventoryViolation {
  kind: string;
  action?: string;
  source?: string;
  declared?: string;
  observed?: string;
  from?: string;
  to?: string;
  tool?: string;
}

/** The declared side of a record, extracted from a valid passport. */
export interface InventoryDeclared {
  principal: string;
  target_systems: string[];
  actions: string[];
  handoffs: string[];
}

/** Kind-tagged untrust reason from the signed-passport verifier (Contrat-3).
 *  Only the fields for a given `kind` are present: `scope_overreach` carries the
 *  extra (declared-beyond-delegated) scope, `malformed_field` names the offending
 *  field. Mirrors the Rust `UntrustReason` (tag = "kind", snake_case). */
export type InventoryUntrustReason =
  | { kind: "bad_signature" }
  | { kind: "expired" }
  | { kind: "empty_delegation" }
  | { kind: "no_human_principal" }
  | { kind: "scope_overreach"; extra: string[] }
  | { kind: "unknown_key_id" }
  | { kind: "malformed_field"; field: string };

/** Kind-tagged signed-attestation situation of a scanned agent -- the axis
 *  ORTHOGONAL to `InventoryPassport` (the manifest axis). Reads the signed
 *  `.inspect_ia_agents/passport.json`: `unsigned` (no signed credential),
 *  `trusted` (parsed and verified), `untrusted` (parsed but failed verification,
 *  carrying the typed reasons WHY), `malformed` (present but unparseable). An
 *  agent has a manifest situation AND an attestation situation; neither implies
 *  the other. Mirrors the Rust `Attestation` (tag = "kind", snake_case). */
export type InventoryAttestation =
  | { kind: "unsigned" }
  | { kind: "trusted" }
  | { kind: "untrusted"; reasons: InventoryUntrustReason[] }
  | { kind: "malformed"; message: string };

/** One identified agent in the inventory. */
export interface InventoryAgent {
  agent_id: string;
  passport: InventoryPassport;
  /** Signed-credential situation (orthogonal to `passport`, the manifest axis). */
  attestation: InventoryAttestation;
  kind: string | null;
  declared: InventoryDeclared | null;
  observed: { actions: string[]; egress: string[] };
  conformity: InventoryConformity;
  evidence: string[];
}

/** Declared vs observed communication edges; undeclared and via-gateway split. */
export interface InventoryCommGraph {
  declared_edges: InventoryEdge[];
  observed_edges: InventoryEdge[];
  undeclared_edges: InventoryEdge[];
  via_gateway_edges: InventoryEdge[];
}

/** The correlated agent inventory (discoveryprobe-inventory AgentInventory). */
export interface AgentInventory {
  schema_version: string;
  agents: InventoryAgent[];
  comm_graph: InventoryCommGraph;
  summary: {
    with_passport: number;
    without_passport: number;
    invalid_passport: number;
    violation_count: number;
    /** Records whose signed passport.json verified trusted (SIGNED axis). */
    attested_trusted: number;
    /** Records whose signed passport.json is present but not trusted. */
    attested_untrusted: number;
    /** Records with no signed passport.json at all. */
    unsigned: number;
    /** Records whose signed passport.json is present but unparseable. */
    attested_malformed: number;
  };
}

/** GET /probe/inventory response: the AgentInventory plus whether it is a LIVE
 *  scan of real agent-source trees (`live: true`) or the committed sample
 *  fallback (`live: false`, with a `reason`) when the Rust engine is not built. */
export interface InventoryResponse {
  inventory: AgentInventory;
  live: boolean;
  engine: string;
  reason?: string;
}

/** GET /probe/inventory: a LIVE scan (the Rust engine walks the configured
 *  agent-source trees on demand and the results are merged), or the committed
 *  sample when the engine is not built. Read-only. */
export function getInventory(): Promise<InventoryResponse> {
  return request<InventoryResponse>("/probe/inventory");
}

// --- Behavioral-analysis engine (POST /behavior/wave) ---

/** A single lens finding in a behavioral wave, with its OWASP/ATLAS tag. */
export interface BehaviorFinding {
  lens: string;
  severity: "alert" | "warn" | "info";
  log: string;
  why: string;
  owasp_asi: string | null;
  mitre_atlas: string | null;
}

/** Per-agent report of a wave: the three-way + score + findings. */
export interface BehaviorAgentReport {
  agent_id: string;
  identified: boolean;
  coherent: boolean;
  behavioral_score: number;
  planned: { systems: string[]; scope: string[] };
  said: { actions: string[] } | null;
  done: {
    dialed_servers: string[];
    undeclared_egress: string[];
    undeclared_dns: string[];
    process_spawned: boolean;
    credential_opens: string[];
    doh_egress: string[];
  };
  findings: BehaviorFinding[];
}

export interface BehaviorReport {
  profile_name: string;
  threat: string;
  evidence_hash: string;
  profile_hash: string;
  tool_version: string;
  experiment_id: string;
  agents: BehaviorAgentReport[];
}

/** Research metrics, present only when the wave was given ground-truth labels. */
export interface BehaviorMetrics {
  confusion: {
    tp: number;
    fp: number;
    fn: number;
    tn: number;
    precision: number;
    recall: number;
    f1: number;
    accuracy: number;
  };
  separation_auc: number;
  roc: { points: Array<{ cutoff: number; tpr: number; fpr: number }>; auc: number };
  standards_distribution: {
    owasp_asi: Record<string, number>;
    mitre_atlas: Record<string, number>;
  };
}

export interface BehaviorWaveResult {
  report: BehaviorReport;
  metrics: BehaviorMetrics | null;
  cohort?: { mode: string | null; agents: string[] };
}

/** The four-knob profile the console sends. All fields optional -> engine defaults. */
export interface BehaviorProfile {
  name?: string;
  lenses?: string[];
  thresholds?: Record<string, string | number>;
  cohort?: { agents?: string[]; discovery?: "detected" | "flagged" };
  threat?: string;
}

export interface BehaviorDefaults {
  lenses: string[];
  threats: string[];
  default_thresholds: Record<string, string | number>;
}

/** GET /behavior/profile/defaults: the catalog (lenses, threats, default thresholds)
 *  the console needs to build a profile editor. */
export function getBehaviorDefaults(): Promise<BehaviorDefaults> {
  return request<BehaviorDefaults>("/behavior/profile/defaults");
}

/** POST /behavior/wave: run a tunable behavioral-analysis wave over a recording.
 *  The API assembles the evidence (registry + declared plan) and runs the
 *  deterministic engine. ground_truth is optional (enables the metrics block). */
export function runBehaviorWave(
  recording: unknown,
  profile: BehaviorProfile,
  groundTruth?: Record<string, { expected_verdict: string }>,
): Promise<BehaviorWaveResult> {
  return request<BehaviorWaveResult>("/behavior/wave", {
    method: "POST",
    body: JSON.stringify({ recording, profile, ground_truth: groundTruth ?? {} }),
  });
}

// --- Correlation engine (POST /behavior/correlate) ---

/** One row in the correlation quadrant table: the per-agent join between the
 *  static discovery scan and the runtime behavioral wave. */
export interface CorrelationRow {
  agent_id: string;
  discovery_subject: string | null;
  static_flagged: boolean;
  runtime_dirty: boolean;
  behavioral_score: number;
  quadrant: "agree_clean" | "static_blind" | "static_overflag" | "agree_dirty";
  agreement: boolean;
}

/** The 2x2 quadrant bucketing: agree_clean/agree_dirty are counts (no
 *  individual detail needed); static_blind/static_overflag carry agent_id lists
 *  because they are the headline anomalies. */
export interface CorrelationQuadrants {
  agree_clean: number;
  agree_dirty: number;
  static_blind: string[];
  static_overflag: string[];
}

/** An unresolved link: the agent could not be placed in a quadrant because one
 *  side (discovery or behavioral evidence) is missing. Rendered fail-loud. */
export interface CorrelationUnresolved {
  agent_id: string;
  reason: "discovery_missing" | "evidence_missing";
}

/** A discovery subject present in the corpus but not wired to any agent link. */
export interface CorrelationCoverageGap {
  discovery_subject: string;
}

/** Full correlation report returned by POST /behavior/correlate. The envelope
 *  key is `correlation`; this interface represents the unwrapped payload. */
export interface CorrelationReport {
  rows: CorrelationRow[];
  quadrants: CorrelationQuadrants;
  unresolved: CorrelationUnresolved[];
  coverage_gaps: CorrelationCoverageGap[];
  thresholds: { runtime_dirty: number };
  tool_version: string;
}

/** Request body for POST /behavior/correlate. */
export interface CorrelateRequest {
  /** Omit (or null) to correlate from the frozen corpus twins (P3 corpus mode);
   *  pass a probe recording to correlate that live capture (P1 live mode). */
  recording?: unknown;
  profile?: BehaviorProfile;
  thresholds?: { runtime_dirty?: number };
}

/** POST /behavior/correlate: run a behavioral wave then correlate with the
 *  static discovery scan through the agent identity map. Returns the quadrant
 *  report (envelope key: `correlation`). The `.correlation` envelope is unwrapped
 *  here so callers receive the bare CorrelationReport. */
export function correlateBehavior(req: CorrelateRequest): Promise<CorrelationReport> {
  return request<{ report: unknown; correlation: CorrelationReport }>("/behavior/correlate", {
    method: "POST",
    body: JSON.stringify(req),
  }).then((r) => r.correlation);
}

/** One captured in-process LLM decision (the hook surface): intent + ops metrics. */
export interface LlmTrace {
  seq: number;
  event_id: string;
  agent_id: string;
  model: string;
  kind: string;
  tool_name: string | null;
  resource: string;
  intent: string;
  /** The model's stated rationale for this decision (declared, unverified).
   *  Optional: traces captured before the field existed do not carry it. */
  rationale?: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  latency_ms: number;
  error: string | null;
}

export interface LlmTracesResult {
  run_id: string;
  traces: LlmTrace[];
  count: number;
}

/** GET /capture/llm-traces: the in-process hook capture for a run (the hook
 *  surface, complementary to the eBPF wire surface). */
export function getLlmTraces(runId: string): Promise<LlmTracesResult> {
  return request<LlmTracesResult>(`/capture/llm-traces?run_id=${encodeURIComponent(runId)}`);
}

export interface CorpusSubject {
  agent_id: string;
  name: string | null;
  family: string;
  target_systems: string[];
  manifest_file: string;
  category: string | null;
  violation_type: string | null;
  expected_verdict: string | null;
}

export interface CorpusListing {
  count: number;
  families: Record<string, number>;
  subjects: CorpusSubject[];
}

/** GET /subjects: the unified corpus across families (git_agent, maf_agent,
 *  maf_orchestration), each with its ground-truth posture. */
export function listSubjects(): Promise<CorpusListing> {
  return request<CorpusListing>("/subjects");
}

export interface SubjectDetail {
  agent_id: string;
  family: string;
  manifest_file: string;
  /** The declared manifest, as stored on disk (free-form per family). */
  manifest: Record<string, unknown>;
  /** The ground-truth posture (4 dimensions, verdict, violation_type); {} if none. */
  ground_truth: Record<string, unknown>;
}

/** GET /subjects/{id}: full manifest + ground-truth of one corpus subject. */
export function getSubjectDetail(agentId: string): Promise<SubjectDetail> {
  return request<SubjectDetail>(`/subjects/${encodeURIComponent(agentId)}`);
}

export interface RunViewStep {
  index: number;
  kind: "handoff" | "turn" | "tool";
  label: string;
  from?: string;
  to?: string;
  /** Declared reason of a handoff (why the source transferred); "" when omitted. */
  reason?: string;
  agent?: string;
  tool?: string | null;
  target?: string;
  approved?: boolean;
}

export interface RunView {
  agent_id: string;
  name: string;
  style: string;
  verdict: string;
  dimensions: { identity: boolean; capabilities: boolean; policy: boolean; behavior: boolean };
  violations: { observed_action: string; kind: string; note: string }[];
  steps: RunViewStep[];
  mermaid: string;
}

/** GET /subjects/orchestration/{id}: step-through view of an orchestration run
 *  (timeline + four-dimension verdict + Mermaid diagram). */
export function getOrchestrationView(agentId: string): Promise<RunView> {
  return request<RunView>(`/subjects/orchestration/${encodeURIComponent(agentId)}`);
}

export interface BenchmarkArea {
  total: number;
  passed: number;
  false_positives: number;
  false_negatives: number;
  dimension_accuracy: { identity: number; capabilities: number; policy: number; behavior: number };
}

export interface Benchmark {
  identification: BenchmarkArea;
  maf: BenchmarkArea;
  orchestration: BenchmarkArea & { by_style: Record<string, BenchmarkArea> };
}

/** GET /subjects/benchmark: judge-accuracy benchmark per dimension / style / area. */
export function getBenchmark(): Promise<Benchmark> {
  return request<Benchmark>("/subjects/benchmark");
}

export interface SimRunSummary {
  agent_id: string;
  name: string;
  verdict: string;
  stopped_reason: string;
}

export interface SimView {
  agent_id: string;
  name: string;
  stopped_reason: string;
  verdict: string;
  dimensions: { identity: boolean; capabilities: boolean; policy: boolean; behavior: boolean };
  turns: { index: number; role: string; content: string }[];
  actions: {
    seq: number;
    agent: string;
    action: string;
    tool_kind: string | null;
    target: string;
    approved: boolean;
  }[];
  checks: { passed: boolean; reason: string }[];
}

/** GET /sim/runs: the committed red-team / simulation runs. */
export function getSimRuns(): Promise<{ count: number; runs: SimRunSummary[] }> {
  return request<{ count: number; runs: SimRunSummary[] }>("/sim/runs");
}

/** GET /sim/runs/{id}: the step-through view of one recorded run. */
export function getSimView(agentId: string): Promise<SimView> {
  return request<SimView>(`/sim/runs/${encodeURIComponent(agentId)}`);
}

/** The four recette dimensions of a judged subject: true = conform, false =
 *  the broken axis (the anomaly). Mirrors the AgentActionEvent judging. */
export interface SimDimensions {
  identity: boolean;
  capabilities: boolean;
  policy: boolean;
  behavior: boolean;
}

export interface SimScenario {
  scenario_id: string;
  name: string;
  verdict: string;
  expected_verdict: string;
  /** Predicted broken dimension (the recette's derived violation), or null. */
  violation_type: string | null;
  /** Ground-truth broken dimension the scenario expects, or null. Lets the UI
   *  show WHY a scenario is a miss: caught the wrong axis vs the expected one. */
  expected_violation_type?: string | null;
  /** True when the recette caught the anomaly for the RIGHT reason: the
   *  predicted verdict matches AND (for a negative) the predicted broken
   *  dimension equals expected_violation_type. */
  anomaly_caught: boolean;
  /** Standards mapping, e.g. { owasp_asi, mitre_atlas, nist }. May be partial. */
  tags: Record<string, string>;
  /** Agent family: "maf" (tool/handoff subjects) or "git" (Lane B agents). */
  family?: string;
}

/**
 * One scenario's full red-team detail. MAF scenarios carry a `transcript` (the
 * Crescendo escalation between the adversary `user`, the `assistant` and `tool`
 * turns); git scenarios carry a `goal` instead. Both carry the four-dimension
 * matrix and the ordered `action_log` the subject actually took (the unapproved
 * / out-of-scope action is the anomaly). Fields are typed optional because the
 * shape differs by family.
 */
export interface SimScenarioView extends SimScenario {
  /** The judged four-dimension matrix; the broken axis is the anomaly. */
  dimensions: SimDimensions;
  /** MAF only: the replayed adversarial conversation, in order. */
  transcript?: { role: string; content: string; tool_name: string | null }[];
  /** Git only: the natural-language objective the agent was driven toward. */
  goal?: string;
  /** The ordered actions the subject took (MAF: invoke_tool rows; git: gateway
   *  actions). Free-form per family; the out-of-scope/unapproved one is flagged. */
  action_log?: Record<string, unknown>[];
  /** The agent's DECLARED capabilities verbatim from the spec/manifest. MAF
   *  entries carry {action, tool_kind, target, approval}; git entries carry
   *  {action, mode, resources}. Lets the UI show declared-vs-actual + I6 gating. */
  capability_scope?: Record<string, unknown>[];
  /** The JUDGE's per-action capability violations (the real anomalies). Each
   *  observed_action names the undeclared tool/handoff (MAF, e.g.
   *  "invoke_tool:None:push") or the out-of-scope action_type (git, e.g.
   *  "open_pr"). Used to mark a row hors-perimetre -- NOT a naive approved===false. */
  violations?: { observed_action: string; note: string }[];
}

/** GET /sim/scenarios: every MAF red-team scenario with its verdict and whether
 *  the recette caught the anomaly. */
export function getSimScenarios(): Promise<{ count: number; scenarios: SimScenario[] }> {
  return request<{ count: number; scenarios: SimScenario[] }>("/sim/scenarios");
}

/** GET /sim/scenarios/{id}: one MAF scenario's outcome plus its replayed
 *  transcript, four-dimension matrix and action log. */
export function getSimScenario(id: string): Promise<SimScenarioView> {
  return request<SimScenarioView>(`/sim/scenarios/${encodeURIComponent(id)}`);
}

/** GET /sim/git-scenarios: every git (Lane B) red-team scenario. Mirrors the
 *  MAF list; each entry carries family:"git". */
export function getSimGitScenarios(): Promise<{ count: number; scenarios: SimScenario[] }> {
  return request<{ count: number; scenarios: SimScenario[] }>("/sim/git-scenarios");
}

/** GET /sim/git-scenarios/{id}: one git scenario's outcome plus its goal,
 *  four-dimension matrix and action log (the gateway actions it took). */
export function getSimGitScenario(id: string): Promise<SimScenarioView> {
  return request<SimScenarioView>(`/sim/git-scenarios/${encodeURIComponent(id)}`);
}

/** The corpus subject created by promoting a caught anomaly. */
export interface SimPromoteResult {
  slug: string;
  created: string[];
  verdict: string;
  violation_type: string | null;
}

/**
 * POST /sim/scenarios/{id}/promote: freeze a caught anomaly (verdict=incorrect,
 * single-axis) into a negative corpus subject, closing the recette loop.
 * Resolves with the created corpus paths. Rejects (ApiError) on 404 (unknown
 * scenario), 422 (true-negative / multi-axis), or 409 (already promoted).
 *
 * Pass { overwrite: true } to re-promote an already-existing subject (the
 * backend's ?overwrite=true replace path), turning the 409 conflict into a
 * deliberate replace.
 */
export function promoteSimScenario(
  id: string,
  opts?: { overwrite?: boolean },
): Promise<SimPromoteResult> {
  const path = opts?.overwrite
    ? withQuery(`/sim/scenarios/${encodeURIComponent(id)}/promote`, { overwrite: "true" })
    : `/sim/scenarios/${encodeURIComponent(id)}/promote`;
  return request<SimPromoteResult>(path, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

/** WS-C: list the observability traces (one per persisted run). Raw JSON. */
export function listObservabilityTraces(): Promise<ObservabilityTraceSummary[]> {
  return request<ObservabilityTraceSummary[]>("/observability/traces", {
    method: "GET",
  });
}

/** WS-C: fetch the full span tree of one trace. Raw JSON, no envelope. */
export function getObservabilityTrace(traceId: string): Promise<ObservabilityTrace> {
  return request<ObservabilityTrace>(
    `/observability/traces/${encodeURIComponent(traceId)}`,
    { method: "GET" },
  );
}

/** Dry-run: execute an inline agent's mock scenario without persisting, and
 *  return the action log it WOULD produce. Raw JSON; rejects (ApiError 400)
 *  on a real-AI agent, missing fields, or no scenario. */
export function dryRunAgent(agent: AgentConfig): Promise<DryRunResult> {
  return request<DryRunResult>("/runs/dry-run", {
    method: "POST",
    body: JSON.stringify(agent),
  });
}

/** Control plane governance digest (counts of verdicts / approvals / execution
 *  over the audit log). Raw JSON, no envelope. */
export function getControlSummary(): Promise<ControlSummary> {
  return request<ControlSummary>("/control/summary", { method: "GET" });
}

/** Operational metrics over captured traces (per-agent / per-tool latency,
 *  error rate, tokens, cost). Raw JSON, no envelope. */
export function getMetricsSummary(): Promise<MetricsSummary> {
  return request<MetricsSummary>("/metrics/summary", { method: "GET" });
}

/** The interaction graph + graph metrics of an orchestration subject's run. */
export function getOrchestrationGraph(agentId: string): Promise<OrchestrationGraph> {
  return request<OrchestrationGraph>(
    `/subjects/orchestration/${encodeURIComponent(agentId)}/graph`,
    { method: "GET" },
  );
}

/** The generated agent registry (one row per corpus subject + metadata). */
export function getAgentRegistry(): Promise<AgentRegistry> {
  return request<AgentRegistry>("/registry/agents", { method: "GET" });
}

/** Token-rich OTLP/JSON GenAI spans for a run's captured traces (gen_ai.usage
 *  tokens + cost), interoperable with any OTel backend. Empty doc for an
 *  unknown run. */
export function getCaptureOtlp(runId: string): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>(
    `/capture/otlp?run_id=${encodeURIComponent(runId)}`,
    { method: "GET" },
  );
}

/** Content-free context receipts of the recorded side effects (intent + body
 *  size/digest, never the bodies). Optional run_id / tail narrowing. */
export function getContextReceipts(runId?: string, tail?: number): Promise<ReceiptsResponse> {
  const path = withQuery("/proxy/receipts", { run_id: runId, tail });
  return request<ReceiptsResponse>(path, { method: "GET" });
}

/** Verify the context-receipt hash chain (sequence-integrity proof). */
export function verifyContextReceipts(runId?: string): Promise<ChainReport> {
  const path = withQuery("/proxy/receipts/verify", { run_id: runId });
  return request<ChainReport>(path, { method: "GET" });
}

/** A transferable, Ed25519-signed export of the chained context receipts.
 *  Unsigned (signed:false) when no signing key is configured (fail-safe). */
export function exportContextReceipts(runId?: string): Promise<Record<string, unknown>> {
  const path = withQuery("/proxy/receipts/export", { run_id: runId });
  return request<Record<string, unknown>>(path, { method: "GET" });
}

/** The verdict of cross-verifying an imported export envelope (off-platform proof). */
export interface ReceiptImportVerdict {
  signature: { valid: boolean; reason: string };
  chain: ChainReport;
}

/** Cross-verify a third-party receipt export: re-checks the Ed25519 signature
 *  and the receipt hash chain server-side, trusting nothing in the envelope.
 *  ``expectedPublicKey`` pins the signer (key pinning). */
export function verifyImportedReceipts(
  envelope: unknown,
  expectedPublicKey?: string,
): Promise<ReceiptImportVerdict> {
  const path = withQuery("/proxy/receipts/verify-import", {
    expected_public_key: expectedPublicKey,
  });
  return request<ReceiptImportVerdict>(path, {
    method: "POST",
    body: JSON.stringify(envelope),
  });
}

// ---------------------------------------------------------------------------
// Runs registry (/results) -- raw JSON, no envelope (plan line 12)
// ---------------------------------------------------------------------------

export interface RunArtifactMeta {
  file: string;
  sha256: string;
}

export interface RunNode {
  id: string;
  kind: string;
  eurodate: string;
  status: string;
}

export interface RunGroup {
  group_id: string;
  eurodate: string;
  label: string;
  status: string;
  runs: RunNode[];
}

export interface RunCategory {
  category: string;
  groups: RunGroup[];
}

export interface RunTree {
  categories: RunCategory[];
}

export interface RunAnnotations {
  tags: string[];
  comment: string;
  label: string;
  retention: string;
}

export interface RunDetail {
  meta: {
    id: string;
    kind: string;
    eurodate: string;
    parent_group: string;
    status: string;
    artifacts: RunArtifactMeta[];
    root_hash: string;
    replay_of: string | null;
  };
  annotations: RunAnnotations;
  artifacts: string[];
}

export function fetchRunTree(): Promise<RunTree> {
  return request<RunTree>("/results/tree", { method: "GET" });
}

export function fetchRun(id: string): Promise<RunDetail> {
  return request<RunDetail>(`/results/${encodeURIComponent(id)}`, { method: "GET" });
}

/** Returns the raw artifact text content. */
export function fetchRunArtifact(id: string, name: string): Promise<string> {
  return request<string>(
    `/results/${encodeURIComponent(id)}/artifact/${encodeURIComponent(name)}`,
    { method: "GET" },
  );
}

export function patchRunAnnotations(
  id: string,
  body: Partial<RunAnnotations>,
): Promise<RunDetail> {
  return request<RunDetail>(`/results/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteRun(id: string): Promise<void> {
  return request<void>(
    withQuery(`/results/${encodeURIComponent(id)}`, { confirm: "true" }),
    { method: "DELETE" },
  );
}

/** POST /results/{id}/replay returns the spawned child run handle (NOT a full
 *  RunDetail): the registry records the child and links it via replay_of. */
export interface ReplayResult {
  child_run_id: string;
  replay_of: string;
  status: string;
  kind: string;
}

export function replayRun(id: string): Promise<ReplayResult> {
  return request<ReplayResult>(`/results/${encodeURIComponent(id)}/replay`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

// ---------------------------------------------------------------------------
// Live multi-agent orchestration (/orchestrate/*) -- Phase 9
// ---------------------------------------------------------------------------

/** One tool call a participant performed during a driven run. */
export interface OrchestrationAction {
  seq: number;
  agent_id: string;
  provider: string;
  model: string;
  target: string;
  tool_kind: string | null;
  approved: boolean;
}

/** One control transfer between participants. */
export interface OrchestrationHop {
  seq: number;
  from: string;
  to: string;
  reason: string;
}

/** Result of POST /orchestrate/run: the tracked, judged run. */
export interface OrchestrationRunResult {
  session_id: string;
  verdict: "correct" | "incorrect";
  dimensions: {
    identity_match: boolean;
    capabilities_conform: boolean;
    policy_compliant: boolean;
    behavior_expected: boolean;
  };
  run: { hops: OrchestrationHop[]; order: string[]; actions: OrchestrationAction[] };
  instances: string[];
}

/** One row of GET /orchestrate/sessions. */
export interface OrchestrationSessionSummary {
  session_id: string;
  instances: string[];
  receipts: number;
}

/** Per-participant provider spec, or a single default backing every participant. */
export interface OrchestrationProviderSpec {
  provider: string;
  model: string;
  base_url?: string;
}

export interface OrchestrationRunRequest {
  team: Record<string, unknown>;
  providers: OrchestrationProviderSpec | Record<string, OrchestrationProviderSpec>;
  session_id: string;
  max_steps?: number;
}

/** Drive a declared team live; returns the tracked + judged run. */
export function runOrchestration(body: OrchestrationRunRequest): Promise<OrchestrationRunResult> {
  return request<OrchestrationRunResult>("/orchestrate/run", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** The orchestration sessions the tracker holds, with their instance roster. */
export function listOrchestrationSessions(): Promise<{ sessions: OrchestrationSessionSummary[] }> {
  return request<{ sessions: OrchestrationSessionSummary[] }>("/orchestrate/sessions", {
    method: "GET",
  });
}
