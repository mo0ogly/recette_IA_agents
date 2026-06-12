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

/**
 * Decision recorded with an audited action (carries the policy version, I4).
 * Shape captured from a real GET /audit/events payload
 * (src/hooks/__fixtures__/auditEvents.fixture.json).
 */
export interface AuditPolicyDecision {
  verdict: PolicyVerdict;
  policy_version: string;
  rule_id: string | null;
}

/**
 * Payload of an audited event. Fields are optional because the payload shape
 * depends on the event kind: action_* events carry the full canonical action,
 * approval_resolved carries a slim resolution record (agent_id, approver,
 * approval_state, correlates_event_id). Derived from the real fixture.
 */
export interface AuditEventPayload {
  agent_id?: string;
  role?: string;
  action_type?: string;
  target_system?: string;
  resource?: string;
  capability_scope?: string[];
  payload?: Record<string, unknown>;
  risk_score?: number;
  risk_level?: string;
  policy_decision?: AuditPolicyDecision | null;
  approval_state?: string;
  side_effect_hash?: string | null;
  correlates_event_id?: string | null;
  approver?: string;
  reason?: string;
  timestamp?: string;
  schema_version?: string;
  extra?: Record<string, unknown>;
  [key: string]: unknown;
}

/** A StoredEvent with its payload typed from the real audit fixture. */
export interface AuditEvent {
  seq: number;
  event_id: string;
  schema_version: string;
  kind: string;
  payload: AuditEventPayload;
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
  /** Target side: "lab" = simulated platform, "real" = real server. */
  runtime: "lab" | "real";
  /** Brain: "mock" = scripted scenario, "real" = live AI (ai_backend). */
  ai_mode?: "mock" | "real";
  /** Identity the agent presents to the target system (Lane B). */
  principal?: string;
  /** External system the agent acts against (e.g. github, gitlab). */
  target_system?: string;
  /** Natural-language objective handed to the agent loop. */
  goal?: string;
  capability_scope?: string[];
  /** Bound AI backend (the AI behind the agent). Used when ai_mode = real. */
  ai_backend_id?: string;
  /** Scripted decisions used when ai_mode = mock. */
  scenario?: Array<Record<string, unknown>>;
  role?: string;
  system_prompt?: string;
  model?: string;
  /** Optional ground truth the verdict judge compares tool results against. */
  ground_truth?: GroundTruth;
}

/** The four correctness dimensions judged by the identification recette. */
export type VerdictDimension = "identity" | "capabilities" | "policy" | "behavior";

/**
 * Ground truth optionally attached to an agent (POST /config/agents).
 * Partial blocks are allowed: the verdict judge only checks declared fields.
 */
export interface GroundTruth {
  detectable?: boolean;
  expected_verdict?: "correct" | "incorrect";
  expected_identity?: string;
  dimensions?: Partial<Record<VerdictDimension, boolean>>;
}

/** One result submitted by an external discovery/identification tool. */
export interface VerdictResult {
  agent_id: string;
  detected?: boolean;
  verdict?: string;
  identity?: string;
  dimensions?: Partial<Record<VerdictDimension, boolean>>;
}

/** Request body of POST /verdicts. */
export interface VerdictSubmissionRequest {
  tool: string;
  results: VerdictResult[];
}

export type JudgedStatus = "PASS" | "FAIL" | "SKIP";

/**
 * One judged entry of a verdict submission: the API's comparison of a tool
 * result against the agent's stored ground truth. checks/expected/observed/
 * evidence_event_ids are absent on SKIP and unknown-agent FAIL entries.
 */
export interface JudgedEntry {
  agent_id: string | null;
  status: JudgedStatus;
  checks?: Record<string, boolean>;
  expected?: Record<string, unknown>;
  observed?: Record<string, unknown>;
  evidence_event_ids?: string[];
  error?: string;
}

/** Latest persisted verdict submission (GET /verdicts; 404 when none). */
export interface VerdictSubmission {
  tool: string | null;
  results: VerdictResult[];
  judged: JudgedEntry[];
  submitted_seq: number;
}

/** Response of POST /verdicts. */
export interface VerdictJudgement {
  judged: JudgedEntry[];
  submitted_seq: number;
}

/**
 * Aggregates over the latest judged submission (GET /verdicts/scorecard).
 * Rates are fractions in [0, 1]; null when no agent carries the check.
 */
export interface VerdictScorecard {
  total: number;
  passed: number;
  skipped: number;
  detection_rate: number | null;
  accuracy_by_dimension: Record<VerdictDimension, number | null>;
  false_positives: number;
  false_negatives: number;
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

/** A run row for the dashboard: status keyed back to its originating agent. */
export interface RunSummary {
  id: string;
  kind: string;
  status: RunStatus;
  agent_id: string | null;
  campaign_id: string | null;
  error: string | null;
}

/** One frame streamed over the run WebSocket (or returned by /events). */
export interface RunEvent {
  type: string;
  [key: string]: unknown;
}

/** One step of a campaign: an agent launch, optionally as a scripted mock. */
export interface CampaignStep {
  agent_id: string;
  stub_script?: Array<Record<string, unknown>>;
}

/** A persisted, ordered set of agent launches run on demand. */
export interface Campaign {
  id: string;
  description: string;
  steps: CampaignStep[];
}

/** A predefined campaign template, named by agent profile + usage. */
export interface CampaignTemplate {
  id: string;
  title: string;
  profile: "legit" | "suspect" | "destructive";
  target_system: string;
  actions: string[];
  agent_id: string;
}

/** Summary of a persisted, replayable recording. */
export interface RecordingMeta {
  recording_id: string;
  agent_id: string;
  target_system: string;
  goal: string;
  provider: string;
  steps: number;
}

/** One executable agent action (what an agent can be made to do). */
export interface AgentAction {
  target_system: string;
  action: string;
  description: string;
  kind: "read" | "bounded_write" | "high_write";
}

/** Providers supported by the platform LLM factory (recette/llm.py). */
export type AiProvider =
  | "anthropic"
  | "openai"
  | "gemini"
  | "groq"
  | "mistral"
  | "deepseek"
  | "xai"
  | "openai_compat";

/** A configured AI backend an agent can be bound to. */
export interface AiBackend {
  id: string;
  provider: AiProvider;
  model: string;
  /** Required when provider = openai_compat (Ollama, vLLM, LiteLLM proxies). */
  base_url?: string;
  /**
   * True when a key is resolvable for this backend: a per-backend secret is
   * stored OR the provider env var is present (openai_compat always true).
   * The key value is NEVER returned by the API; only this boolean (R8).
   */
  key_configured?: boolean;
}

/** Result of POST /config/ai-backends/{id}/test (always 200; ok discriminates). */
export type BackendTestResult =
  | { ok: true; latency_ms: number; kind: string }
  | { ok: false; latency_ms: number; error: string };

/** How a target server is reached: local mock process, declared URL, or SaaS. */
export type ServerMode = "mock_local" | "declared_url" | "real_saas";

/** Live status of a server: process/probe result, or n/a (real_saas). */
export type ServerStatus = "up" | "down" | "n/a";

/** A configured target server agents act against (GET/POST /config/servers). */
export interface ServerEntry {
  id: string;
  /** External system the server emulates or hosts (e.g. github, gitlab). */
  system: string;
  mode: ServerMode;
  /** Required when mode = mock_local: local port of the mock process. */
  port?: number;
  /** Required when mode = declared_url: base URL of the declared server. */
  base_url?: string;
  /** Required when mode = real_saas: org/owner on the SaaS platform. */
  owner?: string;
  /** Name of the env var holding the credential (never the secret itself, R8). */
  auth_env?: string;
}

/** Result of a start/stop lifecycle call; error explains a "down" outcome. */
export interface ServerLifecycleResult {
  status: ServerStatus;
  error?: string;
}

/** One entry of a server's JSONL access log. */
export interface ServerLogLine {
  event_id: string;
  target_system: string;
  action_type: string;
  resource: string;
  status: number;
}

/** Incremental tail of a server access log; next is the cursor to pass back. */
export interface ServerLogTail {
  lines: ServerLogLine[];
  next: number;
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
