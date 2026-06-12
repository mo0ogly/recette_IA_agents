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
  AgentConfig,
  AiBackend,
  ChainReport,
  PendingApproval,
  PolicyDocument,
  StoredEvent,
} from "../types/platform";

const API_BASE_URL: string =
  import.meta.env.VITE_AGENTRAIL_API_URL ?? "http://localhost:8080";

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
  kind?: string;
  agent_id?: string;
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

// ---------------------------------------------------------------------------
// Action catalog and execution
// ---------------------------------------------------------------------------

export function getCatalog(targetSystem?: string): Promise<ActionSpec[]> {
  return request<ActionSpec[]>(
    withQuery("/catalog", { target_system: targetSystem }),
    { method: "GET" },
  );
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
  return request<PendingApproval[]>("/approvals?state=pending", { method: "GET" });
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

export function sweepTimeouts(): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>("/approvals/sweep-timeouts", {
    method: "POST",
  });
}

// ---------------------------------------------------------------------------
// Audit plane (append-only event store, I1)
// ---------------------------------------------------------------------------

export function listAuditEvents(params: AuditEventsParams = {}): Promise<StoredEvent[]> {
  return request<StoredEvent[]>(
    withQuery("/audit/events", {
      from_seq: params.from_seq,
      limit: params.limit,
      kind: params.kind,
      agent_id: params.agent_id,
    }),
    { method: "GET" },
  );
}

export function verifyChain(): Promise<ChainReport> {
  return request<ChainReport>("/audit/verify-chain", { method: "GET" });
}

// ---------------------------------------------------------------------------
// Policies (versioned, I4: decisions record the policy version applied)
// ---------------------------------------------------------------------------

export function listPolicies(): Promise<PolicyDocument[]> {
  return request<PolicyDocument[]>("/policies", { method: "GET" });
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
