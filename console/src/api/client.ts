/**
 * Typed fetch client for the AgentRail platform API.
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
  AiBackend,
  AuditEvent,
  BackendTestResult,
  Campaign,
  CampaignTemplate,
  ChainReport,
  PendingApproval,
  PolicyDocument,
  ProxyDebugStatus,
  ProxyTraceResponse,
  RecordingMeta,
  RunEvent,
  RunHandle,
  RunInfo,
  RunSummary,
  ServerEntry,
  ServerLifecycleResult,
  ServerLogTail,
  ServerStatus,
  ServerTestResult,
  VerdictJudgement,
  RagScorecard,
  VerdictScorecard,
  VerdictSubmission,
  VerdictSubmissionRequest,
} from "../types/platform";

const API_BASE_URL: string =
  import.meta.env.VITE_AGENTRAIL_API_URL ?? "http://localhost:8080";

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

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
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

export function replayRecording(recordingId: string): Promise<RunHandle> {
  return request<RunHandle>(
    `/recordings/${encodeURIComponent(recordingId)}/replay`,
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

/** Recorded side-effect traces (oldest first). tail keeps only the last N. */
export function getProxyTraces(tail?: number): Promise<ProxyTraceResponse> {
  return request<ProxyTraceResponse>(
    withQuery("/proxy/traces", { tail }),
    { method: "GET" },
  );
}

/** Debug toggle state plus the buffered trace count. */
export function getProxyDebugStatus(): Promise<ProxyDebugStatus> {
  return request<ProxyDebugStatus>("/proxy/debug", { method: "GET" });
}

/** Discard the debug trace buffer (the append-only audit log is untouched, I1). */
export function clearProxyTraces(): Promise<{ cleared: boolean }> {
  return request<{ cleared: boolean }>("/proxy/traces", { method: "DELETE" });
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

export interface RecetteScorecard {
  identification: IdentificationScore;
  maf: IdentificationScore;
  discovery: Record<string, DiscoverySurfaceScore>;
  all_passed: boolean;
}

/** GET /subjects/scorecard: aggregate recette verdict over the unified corpus
 *  (identification + MAF + every discovery surface, including mcp). Raw JSON. */
export function getRecetteScorecard(): Promise<RecetteScorecard> {
  return request<RecetteScorecard>("/subjects/scorecard");
}
