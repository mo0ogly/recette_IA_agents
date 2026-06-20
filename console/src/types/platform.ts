/**
 * Contract types for the inspect_ia_agents platform API.
 *
 * These mirror the canonical event model and the platform endpoints.
 * Responses are raw JSON (no { success, data } envelope).
 */

export type PolicyVerdict = "allow" | "deny" | "escalate";

export type ApprovalState = "none" | "pending" | "approved" | "denied" | "timeout";

export type RiskLevel = "low" | "medium" | "high" | "critical";

/**
 * AgentRail default governance posture per governed action (Annex C). A separate
 * axis from risk_level (severity) and verdict (allow/escalate/deny): C1 refuse by
 * default, C2 systematic escalation, C3 conditional authorization, C4
 * authorization with logging.
 */
export type Criticality = "C1" | "C2" | "C3" | "C4";

/** One entry of the action catalog: what an action is and how policy treats it. */
export interface ActionSpec {
  target_system: string;
  action_type: string;
  risk_level: RiskLevel;
  risk_score: number;
  criticality: Criticality;
  criticality_label: string;
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

/**
 * Realtime transport health (GET /events/status). The in-process Phase 1
 * transport is never degraded; a NATS transport may buffer when the bus is
 * unreachable (failure-modes.md). `dropped` counts events evicted from a full
 * backlog -- still recoverable from the durable audit log (I1).
 */
export interface RealtimeStatus {
  degraded: boolean;
  pending: number;
  dropped: number;
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
  /** Optional link to a corpus subject (corpus/agents/<id>) for its ground-truth. */
  corpus_subject_id?: string;
  /**
   * Per-agent pacing: delay in milliseconds (integer >= 0) between successive
   * Lane B actions. Absent/undefined = inherit from the server (or instant);
   * never sent as 0/NaN from an empty input.
   */
  pace_ms?: number;
  /**
   * Optional bounded memory: cap the conversation context fed to the model to
   * a sliding window (the goal message plus the most recent window-1 messages).
   * Absent or disabled = the agent runs with the full context.
   */
  memory?: { enabled: boolean; window: number };
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

/** Response of POST /runs/{id}/submit-verdict (a run pushed onto the board). */
export interface RunVerdictSubmission extends VerdictJudgement {
  run_id: string;
  agent_id: string;
}

/**
 * Read-only recette governance campaign (campaigns/**, GET /recette-campaigns).
 * A DIFFERENT object from the CRUD Campaign ({id, description, steps}): it is a
 * scenario judged by the gateway harness, never run from this UI.
 */
export interface RecetteCampaignSummary {
  id: string;
  family: string;
  name: string;
  objective: string | null;
  teaching: string | null;
  action_count: number;
  agent_count: number;
  /** True when the campaign declares a MAF-team link (macro orchestration campaign). */
  linked?: boolean;
  /** Set only when the file failed to parse/validate (surfaced, not hidden). */
  error?: string;
}

/** A macro orchestration campaign's binding to a MAF team it agrees with on a gate. */
export interface RecetteCampaignLink {
  kind: "maf_orchestration";
  team: string;
  shared_action: string;
  invariant?: string;
  note?: string;
}

/** One scored action of a recette campaign (expect = the awaited verdict). */
export interface RecetteCampaignAction {
  agent_id: string;
  target_system: string;
  action_type: string;
  resource: string;
  expect?: PolicyVerdict;
  rationale?: string;
  payload?: Record<string, unknown>;
}

/** Full recette campaign document (GET /recette-campaigns/{id}). */
export interface RecetteCampaignDetail {
  family: string;
  name: string;
  objective?: string;
  teaching?: string;
  agents: Array<{ id: string; runtime: string; [key: string]: unknown }>;
  actions: RecetteCampaignAction[];
  /** Declared MAF-team links (present on a macro orchestration campaign). */
  links?: RecetteCampaignLink[];
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

// Matches the backend RunManager lifecycle (recette/api/runs.py): a run is
// created "pending", goes "running", then settles "completed" / "failed" /
// "stopped".
export type RunStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "stopped";

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
  /** Wall-clock creation time (ISO 8601, UTC); operational metadata. */
  created_at?: string;
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
  | "openrouter"
  | "together"
  | "fireworks"
  | "moonshot"
  | "zai"
  | "dashscope"
  | "nvidia"
  | "nous"
  | "ollama_cloud"
  | "novita"
  | "stepfun"
  | "arcee"
  | "xiaomi"
  | "gmi"
  | "huggingface"
  | "minimax"
  | "minimax_cn"
  | "opencode_zen"
  | "kilocode"
  | "alibaba_coding_plan"
  | "qwen"
  | "bedrock"
  | "openai_compat";

/** One provider entry in the dynamic catalog served by GET /config/ai-providers.
 *
 * The console builds its provider dropdown from this list (not a hard-kept copy),
 * so a vendor added to the backend factory appears in the UX with no frontend
 * edit. `env_key` is only a hint (the write-only key var, R8); `base_url` is
 * "required" (openai_compat), "optional" (bedrock region), or null. */
export interface AiProviderInfo {
  id: string;
  env_key: string | null;
  key_required: boolean;
  base_url: "required" | "optional" | null;
  /** Known model ids offered as a dropdown (first = default). Empty when the
   * backend curates none for this provider -> the console shows a free-text
   * model field. A "custom" path is always kept so an unlisted id stays typeable. */
  models: string[];
  /** The model preselected when this provider is picked (first of `models`), or
   * null when no models are curated. */
  default_model: string | null;
}

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

/** Result of POST /config/ai-backends/{id}/test (always 200; ok discriminates).
 *  text is the model's answer (the connectivity ping word, or the reply to a
 *  free-text prompt). It is present on every ok outcome; optional for forward
 *  compatibility with older payloads. The provider key never appears here (R8). */
export type BackendTestResult =
  | { ok: true; latency_ms: number; kind: string; text?: string }
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
  /**
   * Fully-qualified domain name the server answers to (private DNS resolver).
   * Optional: not every server declares one.
   */
  fqdn?: string;
  /** Additional names that resolve to this server (private DNS allowlist). */
  aliases?: string[];
  /**
   * Per-server pacing: delay in milliseconds (integer >= 0) inherited as the
   * default by every agent acting against this server. Absent/undefined =
   * instant; never sent as 0/NaN from an empty input.
   */
  pace_ms?: number;
}

/** Global private-DNS containment flag (GET/PUT /config/containment).
 *  Raw shape: no { success, data } envelope. */
export interface ContainmentState {
  containment: boolean;
}

/** Result of POST /config/resolve: how a name maps to a server through the
 *  private-DNS allowlist. Raw dict, no { success, data } envelope. A DENIED
 *  probe is a successful diagnostic (resolved=false + reason), never an error. */
export interface ResolveResult {
  name: string;
  resolved: boolean;
  /** Why a name did not resolve: outside the allowlist, or unknown legacy id. */
  reason?: "not_in_allowlist" | "unknown_legacy";
  /** Server id the name resolved to (resolved=true). */
  server_id?: string;
  /** Canonical fqdn of the resolved server, when it declares one. */
  fqdn?: string | null;
}

/** Result of a start/stop lifecycle call; error explains a "down" outcome. */
export interface ServerLifecycleResult {
  status: ServerStatus;
  error?: string;
}

/** Result of POST /config/servers/{id}/test: one diagnostic action fired at
 *  the server through the I5 proxy path. Fail-safe: ok=false carries error and
 *  no response (server down, bad action, transport failure). */
export interface ServerTestResult {
  ok: boolean;
  latency_ms: number;
  /** Upstream HTTP status (0 when the call never reached the server). */
  status_code?: number;
  /** Raw server response body when ok=true. */
  response?: Record<string, unknown>;
  /** Audit hash of the produced side effect (I1/I5) when ok=true. */
  side_effect_hash?: string | null;
  /** Explanation when ok=false. */
  error?: string | null;
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

/**
 * One recorded side-effect proxy execution (I5 debug trace). Mirrors the
 * backend ProxyTrace: the request intent (event fields) plus the outcome. A
 * trace is a read-only view over execution (I1); the console never mutates it.
 */
export interface ProxyTrace {
  seq: number;
  event_id: string;
  timestamp: string;
  agent_id: string;
  target_system: string;
  action_type: string;
  resource: string;
  request_payload: Record<string, unknown>;
  ok: boolean;
  status_code: number;
  side_effect_hash: string | null;
  error: string | null;
  /** Originating run (F3 run <-> traces link); null for non-run side effects. */
  run_id: string | null;
  /** The server's response body -- the other half of the agent <-> server
   *  exchange (the request is `request_payload`). Empty when the call failed
   *  before a response or the action returned no body. */
  response: Record<string, unknown>;
}

/** Response of GET /proxy/traces: the recorded traces plus the debug toggle. */
export interface ProxyTraceResponse {
  debug_enabled: boolean;
  traces: ProxyTrace[];
}

/** One typed capability gap between declared scope and a real action (F1). */
export interface CapabilityViolation {
  observed_action: string;
  /** undeclared_action | mode_escalation | out_of_scope_resource. */
  kind: string;
  note: string;
}

/** Response of GET /runs/{id}/verdict: the run judged against the agent's
 *  declared manifest on the 4 recette dimensions (F1). */
export interface RunVerdict {
  run_id: string;
  agent_id: string;
  action_count: number;
  verdict: "correct" | "incorrect";
  dimensions: {
    identity: boolean;
    capabilities: boolean;
    policy: boolean;
    behavior: boolean;
  };
  capability_violations: CapabilityViolation[];
}

/** Response of GET /proxy/debug: the toggle state and the buffered trace count. */
export interface ProxyDebugStatus {
  debug_enabled: boolean;
  trace_count: number;
}

/**
 * One intercepted request/response pair from the OPTIONAL mitmproxy wire
 * overlay -- the NETWORK-level view of an I5 side effect (the bytes on the
 * wire), as opposed to ProxyTrace's application-level intent. Read-only (I1).
 */
export interface WireFlow {
  seq: number;
  method: string;
  scheme: string;
  host: string;
  port: number;
  path: string;
  status_code: number;
  ok: boolean;
  content_type: string;
  request_body: string;
  response_body: string;
  /** Originating run when the addon could attribute it; null otherwise. */
  run_id: string | null;
}

/** Response of GET /proxy/wire: the captured flows plus the overlay state. */
export interface WireFlowResponse {
  /** True when INSPECT_IA_AGENTS_WIRE_PROXY is configured (the overlay is wired). */
  enabled: boolean;
  /** The proxy URL agents route through, or null when the overlay is off. */
  proxy_url: string | null;
  flows: WireFlow[];
}

/**
 * Response of GET /proxy/reconcile: the wire<->audit reconciliation.
 *
 * ``ok`` is false when at least one wire flow reached a non-mediated target (no
 * matching audit event -- the ghost-agent signal). ``bypass_flows`` are those
 * unmediated flows; ``audited_run_ids`` are the runs that produced a genuine
 * mediated side effect (the audit-view context).
 */
export interface ReconcileReport {
  run_id: string | null;
  ok: boolean;
  /** Each bypass carries a reason in strict (phase-3) mode: non_mediated_target
   *  (target not mediated at all) or no_audit_event (governed flow to a mediated
   *  target with no matching audit event). */
  bypass_flows: (WireFlow & { bypass_reason?: string })[];
  audited_run_ids: string[];
  /** Echoes whether the phase-3 per-flow side_effect_hash join was used. */
  strict?: boolean;
}

/** Response of GET /proxy/wire/status: overlay state and buffered flow count. */
export interface WireStatus {
  enabled: boolean;
  proxy_url: string | null;
  flow_count: number;
}

/** One selectable transport target for agent side effects (direct vs wire). */
export interface ProxyRouteTarget {
  id: string;
  label: string;
  /** null for the direct route; the overlay URL otherwise. */
  proxy_url: string | null;
}

/** Response of GET /proxy/route: the targets plus the active selection id. */
export interface ProxyRouteState {
  active: string;
  targets: ProxyRouteTarget[];
}

/** One judged query in the RAG retrieval recette (GET /rag/scorecard). */
export interface RagQueryResult {
  query: string;
  retrieved: string[];
  precision: number;
  recall: number;
  top_ok: boolean;
  passed: boolean;
}

/** RAG retrieval-quality scorecard (GET /rag/scorecard). Raw JSON, no envelope. */
export interface RagScorecard {
  total: number;
  passed: number;
  all_passed: boolean;
  mean_precision: number;
  mean_recall: number;
  results: RagQueryResult[];
}

// ---------------------------------------------------------------------------
// Agent catalog registry (GET /catalog/summary): the discovery catalog view.
// This endpoint wraps its payload in the standard { success, data } envelope;
// the client unwraps .data before returning these types (R16).
// ---------------------------------------------------------------------------

/** One registry agent as listed by the catalog summary. */
export interface CatalogAgentSummary {
  name: string;
  version: string;
  publisher_name: string;
  description: string;
  tags: string[];
  /** Declared tool count; 0 marks a tool-less agent (a discovery edge case). */
  tool_count: number;
}

/** Aggregate counts over the registered agents. */
export interface CatalogSummaryCounts {
  total: number;
  unique: number;
  with_tools: number;
  /** The deduplicated union of every agent's tags, sorted. */
  tags: string[];
}

/** The unwrapped payload of GET /catalog/summary (post-envelope). */
export interface CatalogSummary {
  version: string;
  summary: CatalogSummaryCounts;
  agents: CatalogAgentSummary[];
}

/** GET /catalog/rust-summary: the native Rust discovery engine
 *  (discoveryprobe-catalog) run on the same registry. `available` is false when
 *  the binary is not built (fail-safe); when true, `agreement` is whether the
 *  Rust invariant summary equals the Python projection. */
export interface CatalogRustSummary {
  available: boolean;
  engine: string;
  reason?: string;
  summary?: CatalogSummaryCounts;
  python_summary?: CatalogSummaryCounts;
  agreement?: boolean;
}

// ---------------------------------------------------------------------------
// Reperage: observability-tool detection (GET /detect/signatures, POST /detect/scan)
// These endpoints answer with a RAW object (no { success, data } envelope), so
// the client returns the parsed JSON directly -- nothing to unwrap.
// ---------------------------------------------------------------------------

/** One detectable observability tool and the literal needles that betray it. */
export interface DetectSignature {
  tool: string;
  category: string;
  needles: string[];
}

/** The catalog of detectable tools plus the sorted union of their categories. */
export interface DetectSignatures {
  tools: DetectSignature[];
  categories: string[];
}

/** One scan hit: which tool matched and the literal needle that betrayed it. */
export interface DetectMatch {
  tool: string;
  category: string;
  matched: string;
}

/** The result of scanning a text for observability-tool needles. */
export interface DetectScanResult {
  matches: DetectMatch[];
}

// ---------------------------------------------------------------------------
// Discovery overview (GET /discovery/overview): the unified operator dashboard
// that ties the agent catalog together with the observability-reperage tally.
// The endpoint answers with a RAW object (no { success, data } envelope), so the
// client returns the parsed JSON directly -- nothing to unwrap.
// ---------------------------------------------------------------------------

/** The catalog slice of the discovery overview: how many agents are published,
 *  how many declare at least one tool, and how many distinct tags exist. */
export interface DiscoveryCatalogOverview {
  total: number;
  with_tools: number;
  tags: number;
}

/** The reperage slice of the discovery overview: the total count of detectable
 *  observability tools plus two distribution maps -- by detection category and
 *  by governance capability (audit / replay are the governance axis). */
export interface DiscoveryDetectOverview {
  tools: number;
  by_category: Record<string, number>;
  by_capability: Record<string, number>;
}

/** The unwrapped payload of GET /discovery/overview (raw object, no envelope). */
export interface DiscoveryOverview {
  catalog: DiscoveryCatalogOverview;
  detect: DiscoveryDetectOverview;
}

/** WS-C: a single GenAI span in a run's observability trace tree (flat; the
 *  viewer rebuilds the hierarchy from parent_span_id). Times are logical (I4). */
export interface ObservabilitySpan {
  span_id: string;
  parent_span_id: string;
  trace_id: string;
  name: string;
  start_nano: number;
  end_nano: number;
  duration_nano: number;
  attributes: Record<string, string | number>;
}

/** One row in the traces list: a persisted run keyed by a deterministic id. */
export interface ObservabilityTraceSummary {
  trace_id: string;
  recording_id: string;
  agent_id: string | null;
  target_system: string | null;
  provider: string | null;
  span_count: number;
}

/** The full span tree of one recording. */
export interface ObservabilityTrace {
  trace_id: string;
  recording_id: string;
  spans: ObservabilitySpan[];
}

/** Dry-run preview result: the action log a mock scenario WOULD produce,
 *  executed in-memory without persisting (no run record, no event log). */
export interface DryRunResult {
  actions: Array<{
    action_type: string;
    target_system: string;
    resource: string;
    [key: string]: unknown;
  }>;
  tool_results: string[];
  steps: Array<Record<string, unknown>>;
}

/** Control plane governance digest (GET /control/summary): a read-only,
 *  deterministic projection of the audit log (I1/I4). */
export interface ControlSummary {
  total: number;
  verdicts: { allow: number; deny: number; escalate: number };
  approvals: { none: number; pending: number; approved: number; denied: number; timeout: number };
  executed: number;
  denied_execution: number;
  deny_by_default: boolean;
}

/** One metric group (per-agent, per-tool, or totals) over captured traces. */
export interface MetricGroup {
  calls: number;
  errors: number;
  error_rate: number;
  total_tokens: number;
  latency_ms: { p50: number; p95: number; p99: number };
  cost_usd: number | null;
  /** Anomaly flag: "degraded" when the error rate exceeds the threshold. */
  health: "ok" | "degraded";
}

/** Operational metrics digest (GET /metrics/summary): per-agent + per-tool. */
export interface MetricsSummary {
  totals: MetricGroup;
  agents: Record<string, MetricGroup>;
  tools: Record<string, MetricGroup>;
}

/** One node of a multi-agent interaction graph (per-agent graph metrics). */
export interface GraphNode {
  id: string;
  in_degree: number;
  out_degree: number;
  tool_calls: number;
  pagerank: number;
}

/** One weighted directed edge (a handoff source -> target, weight = count). */
export interface GraphEdge {
  source: string;
  target: string;
  weight: number;
}

/** The interaction graph of an orchestration run (nodes + weighted edges). */
export interface OrchestrationGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

/** One row of the generated agent registry (microsoft/discovery-style). */
export interface RegistryAgent {
  agent_id: string;
  name: string | null;
  kind: string;
  family: string;
  version: string | null;
  target_systems: string[];
  capabilities: number;
  standard: string | null;
  publisher: string | null;
  compliance: string[];
  party: string | null;
  tags: string[];
}

/** The generated agent registry (GET /registry/agents): a derived aggregate. */
export interface AgentRegistry {
  generated: boolean;
  count: number;
  agents: RegistryAgent[];
}
