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
//! `Violation`, `scan::PassportStatus`) use UNIFORM kind-tagged JSON:
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
use discoveryprobe_core::CaptureRecording;
use serde::{Deserialize, Serialize};

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
}

/// One identified agent: declared identity, observed behaviour, verdict.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct AgentRecord {
    /// Stable id: passport `agent_id`, else declared principal, else the
    /// last path component of the scanned root (see `correlate` module doc).
    pub agent_id: String,
    /// Passport situation (present / absent / invalid).
    pub passport: PassportStatus,
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
}

/// Runtime-observation input to the correlator. `None` at the correlate call
/// site means a static-only scan.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct ObservedInput {
    /// Per-agent capture recordings (surface keys).
    pub recordings: Vec<CaptureRecording>,
    /// Pre-correlated agent-level communication edges (Task 10 builds these
    /// from raw IPC events; they arrive ready).
    pub observed_edges: Vec<Edge>,
    /// `(agent_id, observed principal)` pairs when a trace carries identity.
    pub observed_principals: Vec<(String, String)>,
}
