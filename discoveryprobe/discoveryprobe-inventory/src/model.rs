//! Data model of the agent inventory: the output contract of the pure
//! correlator (`correlate::correlate`) and its observed-side input.
//!
//! Design reference: `docs/plans/2026-07-04-discoveryprobe-inventory-design.md`
//! section 2. Documented deviations from the design sketch:
//!
//! - `kind` is an `Option<String>` (the passport's `kind()` value, e.g.
//!   "git_agent" / "maf_agent") instead of a dedicated enum: the passport is
//!   the single source of the vocabulary and the bridge consumes strings.
//! - `Observed` carries `actions` + `egress` only. The design's
//!   subprocess/ipc observations arrive pre-correlated as agent-level
//!   `ObservedInput::observed_edges` (Task 10 builds them from raw IPC
//!   events), so raw pid-level fields would be dead weight here (YAGNI).
//! - `evidence` entries are plain strings (relative path + needle, or the
//!   runtime-shadow marker), the same shape `scan::PassportStatus::Absent`
//!   already carries.
//!
//! Serialization: field names are serde-default snake_case (the Python
//! bridge consumes them as-is). Enums crossing the bridge (`Conformity`,
//! `Violation`, `scan::PassportStatus`, `Attestation`, and the re-exported
//! `UntrustReason` it carries) use UNIFORM kind-tagged JSON:
//! internally tagged (`#[serde(tag = "kind")]`), snake_case tags, and no
//! newtype variants (payloads are named fields), so EVERY enum value is a
//! JSON object with a `"kind"` key -- Python dispatches on `value["kind"]`
//! without isinstance checks. Tag vocabulary matches
//! `discoveryprobe_core::ObservationSurface` (snake_case).
//!
//! Determinism (I4): every list is sorted (agents by `agent_id`, violations
//! by their derived `Ord`, edges by `(from, to)`), so the same inputs
//! serialize byte-for-byte identically.

use crate::graph::Edge;
use crate::scan::PassportStatus;
use discoveryprobe_core::ipc::IpcEvents;
use discoveryprobe_core::CaptureRecording;
use serde::{Deserialize, Serialize};

/// Re-export of the pure `agent-passport` untrust reason so a console/Python
/// consumer receives the TYPED reasons (kind-tagged) an `Attestation::Untrusted`
/// carries, without depending on the `agent-passport` crate directly.
pub use agent_passport::UntrustReason;

/// The correlated agent inventory: every identified agent, the declared vs
/// observed communication graph, and roll-up counters.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct AgentInventory {
    /// Inventory schema version ("1.0").
    pub schema_version: String,
    /// One record per identified agent, sorted by `agent_id` (I4).
    pub agents: Vec<AgentRecord>,
    /// Declared vs observed communication edges.
    pub comm_graph: CommGraph,
    /// Roll-up counters derived from `agents`.
    pub summary: InventorySummary,
}

/// Roll-up counters over the agent records (derived, never authoritative).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct InventorySummary {
    /// Records whose passport parsed (`PassportStatus::Present`).
    pub with_passport: usize,
    /// Records with no passport at all (`PassportStatus::Absent`) --
    /// the shadow agents, scanned or runtime-synthesized.
    pub without_passport: usize,
    /// Records whose passport exists but fails validation
    /// (`PassportStatus::Invalid`).
    pub invalid_passport: usize,
    /// Total violations across all records.
    pub violation_count: usize,
    /// Records whose signed `passport.json` verified `Attestation::Trusted`.
    /// Mirrors `with_passport`, but on the SIGNED-CREDENTIAL axis.
    pub attested_trusted: usize,
    /// Records whose signed `passport.json` is present but not trusted
    /// (`Attestation::Untrusted`, including the fail-safe no-keyring default).
    pub attested_untrusted: usize,
    /// Records with no signed `passport.json` at all (`Attestation::Unsigned`).
    pub unsigned: usize,
    /// Records whose signed `passport.json` is present but unparseable
    /// (`Attestation::Malformed`). Mirrors `invalid_passport` on the signed axis.
    pub attested_malformed: usize,
}

/// One identified agent: declared identity, observed behaviour, verdict.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct AgentRecord {
    /// Stable id: passport `agent_id`, else declared principal, else the
    /// last path component of the scanned root (see `correlate` module doc).
    pub agent_id: String,
    /// Manifest situation (present / absent / invalid). Reads
    /// `.inspect_ia_agents/manifest.json` -- a SEPARATE, orthogonal axis from
    /// `attestation`: an agent has a manifest situation AND an attestation
    /// situation, and neither implies the other.
    pub passport: PassportStatus,
    /// Signed-credential situation (unsigned / trusted / untrusted / malformed).
    /// Reads the Contrat-3 `.inspect_ia_agents/passport.json` produced by
    /// `passport issue` and verifies it against the injected keyring + clock.
    /// Orthogonal to `passport` (the manifest axis).
    pub attestation: Attestation,
    /// Subject family from the passport (`git_agent` / `maf_agent`);
    /// `None` when no valid passport exists.
    pub kind: Option<String>,
    /// What the passport declares; `None` without a valid passport.
    pub declared: Option<Declared>,
    /// What the runtime capture observed; empty when static-only.
    pub observed: Observed,
    /// Conformity verdict for this record.
    pub conformity: Conformity,
    /// Auditor-facing proof strings (shadow-agent code evidence, the
    /// runtime-shadow marker); sorted and deduplicated.
    pub evidence: Vec<String>,
}

/// Signed-attestation situation of an agent tree: the verdict of the Contrat-3
/// `.inspect_ia_agents/passport.json` signed credential.
///
/// This is a NEW axis, ORTHOGONAL to [`PassportStatus`] (the manifest axis):
/// `PassportStatus` reads `manifest.json` (present/absent/invalid), while this
/// enum reads the SIGNED `passport.json` produced by `passport issue`. An agent
/// can be a manifest shadow ([`PassportStatus::Absent`]) yet carry a
/// [`Attestation::Trusted`] credential, or the reverse -- the two never imply
/// each other.
///
/// Kind-tagged JSON like every bridge-crossing enum (uniform style, see the
/// module header): each value is an object with a `"kind"` key, so a
/// Python/console consumer dispatches on `value["kind"]` without shape checks.
///
/// # Malformed vs Untrusted (decision)
///
/// A `passport.json` that is PRESENT but does not PARSE (`from_json` errors:
/// corrupt JSON, missing/unknown field, not a passport) is a distinct
/// [`Attestation::Malformed`] -- the parallel of the manifest axis'
/// [`PassportStatus::Invalid`] -- kept separate from
/// [`Attestation::Untrusted`], which is a passport that PARSED but failed
/// verification (bad signature, expired, unknown key, ...). "Present but
/// unparseable" and "parsed but not trusted" are different auditor signals.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum Attestation {
    /// No `.inspect_ia_agents/passport.json` in the tree. The manifest may still
    /// exist (separate axis); the agent simply carries no signed credential.
    Unsigned,
    /// `passport.json` is present, parsed, and verified [`Verdict::Trusted`]
    /// against the injected keyring and clock.
    ///
    /// [`Verdict::Trusted`]: agent_passport::Verdict::Trusted
    Trusted,
    /// `passport.json` is present and parsed, but verification returned
    /// [`Verdict::Untrusted`]: it carries every applicable typed
    /// [`UntrustReason`]. This ALSO covers the fail-safe no-keyring default (a
    /// scan without `--trust`/`--now` cannot establish trust, so a present
    /// passport is [`UntrustReason::UnknownKeyId`], never optimistically
    /// trusted).
    ///
    /// [`Verdict::Untrusted`]: agent_passport::Verdict::Untrusted
    Untrusted {
        /// Every applicable untrust reason, sorted by the [`UntrustReason`]
        /// derived `Ord` (I4), exactly as the pure verifier emits them.
        reasons: Vec<UntrustReason>,
    },
    /// `passport.json` is present but could not be read or parsed as a passport
    /// (corrupt/not-a-passport). The parallel of [`PassportStatus::Invalid`].
    Malformed {
        /// The read/parse error string (auditor-facing).
        message: String,
    },
}

/// The declared side of an agent record, extracted from its passport.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Declared {
    /// Declared principal (or the MAF "provider:model" stand-in).
    pub principal: String,
    /// ALL declared target systems, sorted (plural: a multi-target MAF
    /// agent must not be judged against a single arbitrary target).
    pub target_systems: Vec<String>,
    /// Declared action names, sorted and deduplicated.
    pub actions: Vec<String>,
    /// Declared handoff target agent ids, sorted and deduplicated.
    pub handoffs: Vec<String>,
}

/// The observed side of an agent record, extracted from capture recordings.
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct Observed {
    /// Canonical action names seen in surface keys, sorted and deduplicated.
    pub actions: Vec<String>,
    /// Surface keys with no canonical action prefix (network egress and other
    /// raw evidence), sorted and deduplicated. Evidence only, never a violation.
    pub egress: Vec<String>,
}

/// Conformity verdict of one agent record.
///
/// `NotObserved` is distinct from `Conform`: a static-only scan can NEVER
/// conclude conformity (fail-safe, per the design).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum Conformity {
    /// Observed live and no violation found.
    Conform,
    /// No runtime observation covered this agent; nothing can be concluded.
    NotObserved,
    /// At least one violation.
    Violations {
        /// The violations, sorted by the `Violation` derived order (I4).
        violations: Vec<Violation>,
    },
}

/// One declared-vs-observed violation.
///
/// `ModeEscalation` and `ApprovalBypass` are part of the bridge contract but
/// are produced ONLY when the input carries that signal; the current
/// `CaptureRecording` surface keys carry neither mode nor approval data, so
/// the correlator never fabricates them (see `correlate` module doc, rule 7).
///
/// Derives `Ord`: violations sort by variant declaration order, then by
/// field values -- a stable, documented sort key (I4).
#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum Violation {
    /// Agent code or a live agent exists with no passport (shadow agent).
    PassportAbsent,
    /// An observed canonical action is outside the declared scope.
    UndeclaredAction {
        /// The observed canonical action name.
        action: String,
        /// The observation surface that saw it (e.g. "hook_sdk").
        source: String,
    },
    /// Observed access mode exceeds the declared one (bridge-fed only).
    ModeEscalation {
        /// Declared access mode.
        declared: String,
        /// Observed access mode.
        observed: String,
    },
    /// The observed principal diverges from the declared one (I3).
    PrincipalMismatch {
        /// Declared principal.
        declared: String,
        /// Observed principal.
        observed: String,
    },
    /// An observed communication edge is absent from the declared graph.
    UndeclaredHandoff {
        /// Source agent id of the observed edge.
        from: String,
        /// Target agent id of the observed edge.
        to: String,
    },
    /// An approval-gated tool was invoked without the gate (bridge-fed only).
    ApprovalBypass {
        /// The tool that was invoked.
        tool: String,
    },
}

/// Declared vs observed communication edges. All three lists are sorted and
/// deduplicated (I4).
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct CommGraph {
    /// Edges declared by passports / team.json.
    pub declared_edges: Vec<Edge>,
    /// Edges observed at runtime (pre-correlated agent-level).
    pub observed_edges: Vec<Edge>,
    /// Observed edges absent from the declared set (violations).
    pub undeclared_edges: Vec<Edge>,
    /// Observed edges whose resolved destination agent is a gateway process
    /// (design rule 4): carried SEPARATELY and EXCLUDED from
    /// `undeclared_edges` -- a hop through a declared broker is not an
    /// undeclared direct handoff. Sorted and deduplicated (I4).
    pub via_gateway_edges: Vec<Edge>,
}

/// Runtime-observation input to the correlator. `None` at the correlate call
/// site means a static-only scan.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct ObservedInput {
    /// Per-agent capture recordings (surface keys).
    pub recordings: Vec<CaptureRecording>,
    /// Pre-correlated agent-level communication edges. When present these are
    /// UNIONED (deduped) with the edges the correlator derives from `ipc`.
    #[serde(default)]
    pub observed_edges: Vec<Edge>,
    /// `(agent_id, observed principal)` pairs when a trace carries identity.
    #[serde(default)]
    pub observed_principals: Vec<(String, String)>,
    /// Raw reconciled inter-agent IPC events (Task 9 `IpcEvents`): the
    /// correlator parses these back into pid-level listen/connect/accept/
    /// unix-connect facts and BUILDS agent-level observed edges from them.
    /// Default empty (a static or hook-only run carries none).
    #[serde(default)]
    pub ipc: IpcEvents,
    /// Fork edges `(parent_pid, child_pid)` for fork-tree pid->agent
    /// attribution: a comm from a fork child is attributed to the nearest
    /// ancestor pid that maps to an agent. Default empty.
    #[serde(default)]
    pub forks: Vec<(u32, u32)>,
    /// `pid -> agent_id` mapping (the broker knows which pid runs which
    /// agent). A pid resolves either directly here or via the fork tree.
    /// Default empty (an unresolvable pid drops its edge, never fabricates).
    #[serde(default)]
    pub pid_agents: Vec<(u32, String)>,
    /// Agent ids considered GATEWAYS (R5: config input, never hardcoded). An
    /// IPC edge whose resolved destination agent is in this set is recorded in
    /// `CommGraph::via_gateway_edges`, not as an undeclared direct handoff.
    #[serde(default)]
    pub gateways: Vec<String>,
}
