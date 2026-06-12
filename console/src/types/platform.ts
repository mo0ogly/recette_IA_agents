/**
 * Contract types for the AgentRail platform API.
 *
 * These mirror the canonical event model and the platform endpoints.
 * Responses are raw JSON (no { success, data } envelope).
 */

export type PolicyVerdict = "allow" | "deny" | "escalate";

export type ApprovalState = "none" | "pending" | "approved" | "denied" | "timeout";

export type RiskLevel = "low" | "medium" | "high" | "critical";

/** One entry of the action catalog: what an action is and how policy treats it. */
export interface ActionSpec {
  target_system: string;
  action_type: string;
  risk_level: RiskLevel;
  risk_score: number;
  verdict_privileged: PolicyVerdict;
  verdict_default: PolicyVerdict;
  privileged_roles: string[];
  description: string;
}

/** Outcome of executing one action through the gateway. */
export interface ActionOutcome {
  event_id: string;
  verdict: PolicyVerdict;
  approval_state: ApprovalState;
  risk_level: RiskLevel;
  policy_version: string | null;
  rule_id: string | null;
  executed: boolean;
  result: Record<string, unknown> | null;
  side_effect_hash: string | null;
  error?: string | null;
}

/** An action waiting for human approval (I6: execution is blocked until resolution). */
export interface PendingApproval {
  event_id: string;
  seq: number;
  requested_at: string;
  agent_id: string;
  role: string;
  target_system: string;
  action_type: string;
  resource: string;
  risk_level: string;
  policy_version: string;
}

/** An event as persisted in the append-only event store (I1). */
export interface StoredEvent {
  seq: number;
  event_id: string;
  schema_version: string;
  kind: string;
  payload: Record<string, unknown>;
  prev_hash: string;
  hash: string;
}

/** Result of verifying the event store hash chain. */
export interface ChainReport {
  ok: boolean;
  checked: number;
  first_break_seq: number | null;
  detail: string | null;
}

/** Configuration of a registered agent. */
export interface AgentConfig {
  id: string;
  runtime: "lab" | "real";
  /** Identity the agent presents to the target system (Lane B). */
  principal?: string;
  /** External system the agent acts against (e.g. github, gitlab). */
  target_system?: string;
  /** Natural-language objective handed to the agent loop. */
  goal?: string;
  capability_scope?: string[];
  /** Bound AI backend (the AI behind the agent). Empty when run as a mock. */
  ai_backend_id?: string;
  role?: string;
  system_prompt?: string;
  model?: string;
}

/** A launched agent run (Lane B) or a recette runner (discovery/identification). */
export type RunKind = "lane_b" | "discovery" | "identification";

export type RunStatus = "pending" | "running" | "stopped" | "done" | "error";

export interface RunHandle {
  run_id: string;
  status: RunStatus;
}

export interface RunInfo {
  id: string;
  kind: RunKind;
  status: RunStatus;
  error: string | null;
}

/** One frame streamed over the run WebSocket (or returned by /events). */
export interface RunEvent {
  type: string;
  [key: string]: unknown;
}

/** A configured AI backend an agent can be bound to. */
export interface AiBackend {
  id: string;
  provider: string;
  model: string;
}

/** One rule of a policy document. */
export interface PolicyRule {
  rule_id: string;
  target_system: string;
  action_type: string;
  role: string;
  verdict: PolicyVerdict;
  risk_level: RiskLevel;
}

/** A versioned policy document (the version applied is recorded with each decision, I4). */
export interface PolicyDocument {
  version: string;
  default: string;
  approval_timeout_seconds: number;
  rules: PolicyRule[];
}
