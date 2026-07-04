//! Declared-vs-observed conformity: the PURE correlator producing the
//! `AgentInventory` (design doc section 2). Zero I/O, zero clock, zero
//! randomness (I4): the output is a pure function of the three inputs.
//!
//! Correlation rules (numbered as in the task/design):
//!
//! 1. A `CaptureRecording` matches a scanned record by `agent_id`. A
//!    recording with no matching record synthesizes a RUNTIME shadow record
//!    (`PassportStatus::Absent`, evidence = the runtime-shadow marker): a
//!    live agent without a passport is surfaced, never dropped.
//! 2. Observed actions come from surface keys ("action:resource" or bare).
//!    A key whose prefix (before the first ':') is a canonical git action
//!    (`manifest::KNOWN_GIT_ACTIONS`) is an observed action; outside the
//!    declared scope it is an `UndeclaredAction`. A key with no canonical
//!    prefix is egress evidence only, never a violation. Records WITHOUT a
//!    valid passport get their actions/egress recorded but no
//!    `UndeclaredAction`: with nothing declared there is nothing to compare
//!    -- the passport status itself is the signal (mono-axis).
//! 3. Every `Absent` record carries a `PassportAbsent` violation.
//! 4. `observed_principals` divergent from the declared principal ->
//!    `PrincipalMismatch` (I3). Unlike recordings (rule 1), an observed
//!    principal or edge whose agent id matches no record synthesizes
//!    NOTHING -- intentional asymmetry: a recording proves a live agent, a
//!    bare principal/edge mention alone does not.
//! 5. An observed edge absent from the declared graph -> `UndeclaredHandoff`
//!    attached to the `from` record (when that record exists; the edge is
//!    ALWAYS listed in `comm_graph.undeclared_edges` either way).
//! 6. Conformity: violations -> `Violations` (sorted); no violations, the
//!    agent was seen live (matched recording, observed principal, or an
//!    observed edge touching it) AND it carries a parseable declaration ->
//!    `Conform`; otherwise `NotObserved`. A static-only run
//!    (`observed = None`) can therefore NEVER be `Conform`. Invalid
//!    passport: the Invalid status itself is the signal; with no parseable
//!    declaration the record can never be `Conform` -- it stays
//!    `NotObserved` unless observed data adds violations (fail-safe: a
//!    broken manifest must never outrank a missing one, nor a valid one).
//! 7. `ModeEscalation` / `ApprovalBypass` are NEVER fabricated: the current
//!    `CaptureRecording` surface keys carry no mode/approval signal. The
//!    variants stay in the contract for the bridge (Task 10/13) to populate.
//! 8. Everything is sorted: agents by `agent_id`, violations by their
//!    derived `Ord`, edges by `(from, to)`. The declared graph is
//!    re-normalized on intake (its `edges` field is pub, so callers may
//!    hand over an unsorted set).
//!
//! Agent id derivation (stable, deterministic): passport `agent_id()` when
//! present, else the non-empty declared `principal()`, else the LAST PATH
//! COMPONENT of the scanned root (the tree slug). Two scanned trees deriving
//! the same id keep the FIRST record (input order is part of the input, so
//! determinism holds).
//!
//! Failure mode (fail-safe): missing runtime observation degrades to
//! `NotObserved`, never to a false `Conform`.

use crate::graph::{DeclaredGraph, Edge};
use crate::manifest::KNOWN_GIT_ACTIONS;
use crate::model::{
    AgentInventory, AgentRecord, CommGraph, Conformity, Declared, InventorySummary, Observed,
    ObservedInput, Violation,
};
use crate::scan::{PassportStatus, ScannedAgent};
use discoveryprobe_core::{CaptureRecording, ObservationSurface};
use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;

/// Inventory schema version emitted by the correlator.
pub const SCHEMA_VERSION: &str = "1.0";

/// Evidence string of a runtime shadow record: a live capture matched no
/// scanned source tree (rule 1).
const RUNTIME_SHADOW_EVIDENCE: &str = "observed live (capture) with no source passport";

/// Correlates scanned agents, the declared graph, and optional runtime
/// observation into an `AgentInventory`. Pure: zero I/O, zero clock (I4).
/// `observed = None` means a static-only scan (`NotObserved`, never
/// `Conform`). See the module doc for the numbered correlation rules.
pub fn correlate(
    scanned: &[ScannedAgent],
    declared_graph: &DeclaredGraph,
    observed: Option<&ObservedInput>,
) -> AgentInventory {
    // Rule 8: re-normalize the declared graph defensively (pub field).
    let declared_edges = normalize_edges(declared_graph.edges.clone());

    // Records keyed by agent_id (BTreeMap = sorted output for free, I4).
    let mut records: BTreeMap<String, AgentRecord> = BTreeMap::new();
    for agent in scanned {
        let record = record_from_scanned(agent);
        records.entry(record.agent_id.clone()).or_insert(record);
    }

    // Per-record violations accumulated aside, merged at finalization.
    let mut violations: BTreeMap<String, Vec<Violation>> = BTreeMap::new();
    // Agents touched by ANY live observation (rule 6 Conform precondition).
    let mut observed_ids: BTreeSet<String> = BTreeSet::new();
    let mut observed_edges: Vec<Edge> = Vec::new();
    let mut undeclared_edges: Vec<Edge> = Vec::new();

    if let Some(input) = observed {
        // Rule 1 + 2: recordings drive observed actions/egress; a recording
        // without a scanned record synthesizes a runtime shadow record.
        for recording in &input.recordings {
            observed_ids.insert(recording.agent_id.clone());
            let record = records
                .entry(recording.agent_id.clone())
                .or_insert_with(|| runtime_shadow_record(&recording.agent_id));
            apply_recording(record, recording, &mut violations);
        }
        // Rule 4: observed principal vs declared principal (I3).
        for (agent_id, observed_principal) in &input.observed_principals {
            observed_ids.insert(agent_id.clone());
            if let Some(declared) = records.get(agent_id).and_then(|r| r.declared.as_ref()) {
                if !declared.principal.is_empty() && declared.principal != *observed_principal {
                    violations.entry(agent_id.clone()).or_default().push(
                        Violation::PrincipalMismatch {
                            declared: declared.principal.clone(),
                            observed: observed_principal.clone(),
                        },
                    );
                }
            }
        }
        // Rule 5: observed edges minus declared edges = undeclared handoffs.
        observed_edges = normalize_edges(input.observed_edges.clone());
        for edge in &observed_edges {
            observed_ids.insert(edge.from.clone());
            observed_ids.insert(edge.to.clone());
        }
        undeclared_edges = observed_edges
            .iter()
            .filter(|e| declared_edges.binary_search(e).is_err())
            .cloned()
            .collect();
        for edge in &undeclared_edges {
            if records.contains_key(&edge.from) {
                violations.entry(edge.from.clone()).or_default().push(
                    Violation::UndeclaredHandoff {
                        from: edge.from.clone(),
                        to: edge.to.clone(),
                    },
                );
            }
        }
    }

    // Finalization: rule 3 (PassportAbsent), rule 6 (conformity), rule 8
    // (sorted violations; agents already sorted by the BTreeMap key).
    let observed_present = observed.is_some();
    let agents: Vec<AgentRecord> = records
        .into_values()
        .map(|mut record| {
            let mut record_violations = violations.remove(&record.agent_id).unwrap_or_default();
            if matches!(record.passport, PassportStatus::Absent { .. }) {
                record_violations.push(Violation::PassportAbsent);
            }
            record_violations.sort();
            record_violations.dedup();
            // Conform requires a parseable declaration to compare against:
            // an observed record with `declared == None` (Invalid passport)
            // stays NotObserved (fail-safe, rule 6).
            record.conformity = if !record_violations.is_empty() {
                Conformity::Violations {
                    violations: record_violations,
                }
            } else if observed_present
                && observed_ids.contains(&record.agent_id)
                && record.declared.is_some()
            {
                Conformity::Conform
            } else {
                Conformity::NotObserved
            };
            record
        })
        .collect();

    let summary = summarize(&agents);
    AgentInventory {
        schema_version: SCHEMA_VERSION.to_string(),
        agents,
        comm_graph: CommGraph {
            declared_edges,
            observed_edges,
            undeclared_edges,
        },
        summary,
    }
}

/// Builds the static side of a record from one scanned agent (agent id
/// derivation is documented in the module header).
fn record_from_scanned(agent: &ScannedAgent) -> AgentRecord {
    let (agent_id, kind, declared, evidence) = match &agent.passport {
        PassportStatus::Present { passport } => {
            let agent_id = match passport.agent_id() {
                Some(id) => id.to_string(),
                None => {
                    let principal = passport.principal();
                    if principal.is_empty() {
                        derived_root_id(&agent.root)
                    } else {
                        principal
                    }
                }
            };
            let declared = Declared {
                principal: passport.principal(),
                // PLURAL on purpose: a multi-target MAF agent must not be
                // judged against one arbitrary target.
                target_systems: passport.target_systems(),
                actions: passport.actions(),
                handoffs: passport.handoffs(),
            };
            (
                agent_id,
                Some(passport.kind().to_string()),
                Some(declared),
                Vec::new(),
            )
        }
        PassportStatus::Absent { evidence } => {
            (derived_root_id(&agent.root), None, None, evidence.clone())
        }
        PassportStatus::Invalid { .. } => (derived_root_id(&agent.root), None, None, Vec::new()),
    };
    AgentRecord {
        agent_id,
        passport: agent.passport.clone(),
        kind,
        declared,
        observed: Observed::default(),
        conformity: Conformity::NotObserved, // decided at finalization
        evidence,
    }
}

/// Synthesizes the RUNTIME shadow record for a capture with no scanned
/// source (rule 1): live agent, zero passport, surfaced with evidence.
fn runtime_shadow_record(agent_id: &str) -> AgentRecord {
    AgentRecord {
        agent_id: agent_id.to_string(),
        passport: PassportStatus::Absent {
            evidence: vec![RUNTIME_SHADOW_EVIDENCE.to_string()],
        },
        kind: None,
        declared: None,
        observed: Observed::default(),
        conformity: Conformity::NotObserved, // decided at finalization
        evidence: vec![RUNTIME_SHADOW_EVIDENCE.to_string()],
    }
}

/// Applies one recording to its record (rule 2): canonical-action keys feed
/// `observed.actions` (and `UndeclaredAction` when a declaration exists and
/// excludes them); other keys are egress evidence. Output stays sorted.
fn apply_recording(
    record: &mut AgentRecord,
    recording: &CaptureRecording,
    violations: &mut BTreeMap<String, Vec<Violation>>,
) {
    for (surface, keys) in &recording.surfaces {
        // Defensive dedup: the recording may not have been normalised.
        let unique: BTreeSet<&str> = keys.iter().map(String::as_str).collect();
        for key in unique {
            let prefix = key.split(':').next().unwrap_or(key);
            if KNOWN_GIT_ACTIONS.contains(&prefix) {
                record.observed.actions.push(prefix.to_string());
                if let Some(declared) = &record.declared {
                    // `declared.actions` is sorted+deduped (passport intake):
                    // binary search on the hot path (every key of every recording).
                    if declared
                        .actions
                        .binary_search_by(|a| a.as_str().cmp(prefix))
                        .is_err()
                    {
                        violations.entry(record.agent_id.clone()).or_default().push(
                            Violation::UndeclaredAction {
                                action: prefix.to_string(),
                                source: surface_name(*surface).to_string(),
                            },
                        );
                    }
                }
            } else {
                record.observed.egress.push(key.to_string());
            }
        }
    }
    record.observed.actions.sort();
    record.observed.actions.dedup();
    record.observed.egress.sort();
    record.observed.egress.dedup();
}

/// The bridge name of an observation surface, identical to its serde
/// snake_case rename in `discoveryprobe_core` (single vocabulary).
fn surface_name(surface: ObservationSurface) -> &'static str {
    match surface {
        ObservationSurface::HookSubprocess => "hook_subprocess",
        ObservationSurface::HookMcp => "hook_mcp",
        ObservationSurface::HookSdk => "hook_sdk",
        ObservationSurface::EbpfWire => "ebpf_wire",
    }
}

/// Derived agent id for a passport-less tree: the last path component of the
/// scanned root (the tree slug) -- stable and reproducible from the input.
fn derived_root_id(root: &str) -> String {
    Path::new(root)
        .file_name()
        .and_then(|n| n.to_str())
        .map(str::to_string)
        .unwrap_or_else(|| root.to_string())
}

/// Sorts and deduplicates an edge list (I4 normalization, rule 8).
fn normalize_edges(mut edges: Vec<Edge>) -> Vec<Edge> {
    edges.sort();
    edges.dedup();
    edges
}

/// Derives the roll-up counters from the finalized records.
fn summarize(agents: &[AgentRecord]) -> InventorySummary {
    let mut summary = InventorySummary {
        with_passport: 0,
        without_passport: 0,
        invalid_passport: 0,
        violation_count: 0,
    };
    for record in agents {
        match &record.passport {
            PassportStatus::Present { .. } => summary.with_passport += 1,
            PassportStatus::Absent { .. } => summary.without_passport += 1,
            PassportStatus::Invalid { .. } => summary.invalid_passport += 1,
        }
        if let Conformity::Violations { violations } = &record.conformity {
            summary.violation_count += violations.len();
        }
    }
    summary
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::graph::Edge;
    use crate::manifest::Passport;
    use crate::model::{Conformity, Observed, Violation};
    use crate::scan::{scan_tree, PassportStatus};
    use crate::test_support::corpus_path;
    use discoveryprobe_core::{CaptureRecording, ObservationSurface};

    /// Builds a Present scanned agent from a minimal unified manifest.
    fn present_agent(agent_id: &str, principal: &str, actions: &[&str]) -> ScannedAgent {
        let caps: Vec<String> = actions
            .iter()
            .map(|a| format!(r#"{{"action":"{a}","mode":"write","resources":["acme/*"]}}"#))
            .collect();
        let raw = format!(
            r#"{{"agent_id":"{agent_id}","name":"{agent_id}","target_systems":["github"],"declared_identity":{{"auth_method":"pat","principal":"{principal}"}},"capability_scope":[{}],"version":"1.0.0"}}"#,
            caps.join(",")
        );
        ScannedAgent {
            root: format!("/scan/{agent_id}"),
            passport: PassportStatus::Present {
                passport: Passport::parse(&raw).expect("test passport"),
            },
        }
    }

    /// Builds an Absent (shadow) scanned agent with one evidence string.
    fn shadow_agent(slug: &str) -> ScannedAgent {
        ScannedAgent {
            root: format!("/scan/{slug}"),
            passport: PassportStatus::Absent {
                evidence: vec!["agent/bot.py: import github".to_string()],
            },
        }
    }

    /// Shorthand edge constructor for assertions.
    fn edge(from: &str, to: &str) -> Edge {
        Edge {
            from: from.to_string(),
            to: to.to_string(),
        }
    }

    /// Extracts the violations of a record, panicking on any other verdict.
    fn violations_of(inv: &AgentInventory, agent_id: &str) -> Vec<Violation> {
        let record = inv
            .agents
            .iter()
            .find(|a| a.agent_id == agent_id)
            .unwrap_or_else(|| panic!("no record for {agent_id}"));
        match &record.conformity {
            Conformity::Violations { violations } => violations.clone(),
            other => panic!("expected Violations for {agent_id}, got {other:?}"),
        }
    }

    #[test]
    fn static_only_scan_is_not_observed_never_conform() {
        let inv = correlate(
            &[present_agent("pr-bot", "good-bot", &["open_pr"])],
            &DeclaredGraph::default(),
            None,
        );
        assert_eq!(inv.schema_version, "1.0");
        assert_eq!(inv.agents.len(), 1);
        assert_eq!(inv.agents[0].agent_id, "pr-bot");
        assert_eq!(inv.agents[0].conformity, Conformity::NotObserved);
        assert_eq!(inv.agents[0].observed, Observed::default());
        assert_eq!(inv.summary.with_passport, 1);
        assert_eq!(inv.summary.violation_count, 0);
    }

    #[test]
    fn shadow_agent_yields_passport_absent_violation() {
        let inv = correlate(&[shadow_agent("ghost")], &DeclaredGraph::default(), None);
        assert_eq!(inv.agents.len(), 1);
        assert_eq!(
            violations_of(&inv, "ghost"),
            vec![Violation::PassportAbsent]
        );
        // The scan evidence is propagated onto the record.
        assert_eq!(
            inv.agents[0].evidence,
            vec!["agent/bot.py: import github".to_string()]
        );
        assert_eq!(inv.summary.without_passport, 1);
        assert_eq!(inv.summary.violation_count, 1);
    }

    #[test]
    fn observed_action_outside_scope_is_undeclared_action() {
        let mut rec = CaptureRecording::new("pr-bot");
        rec.observe(ObservationSurface::HookSdk, "push:acme/web");
        let obs = ObservedInput {
            recordings: vec![rec],
            ..Default::default()
        };
        let inv = correlate(
            &[present_agent(
                "pr-bot",
                "good-bot",
                &["open_pr", "read_repo"],
            )],
            &DeclaredGraph::default(),
            Some(&obs),
        );
        assert_eq!(
            violations_of(&inv, "pr-bot"),
            vec![Violation::UndeclaredAction {
                action: "push".to_string(),
                source: "hook_sdk".to_string(),
            }]
        );
        // The observed action is recorded even though it is a violation.
        assert_eq!(inv.agents[0].observed.actions, vec!["push".to_string()]);
    }

    #[test]
    fn observed_edge_outside_declared_graph_is_undeclared_handoff() {
        let declared = DeclaredGraph {
            edges: vec![edge("a", "b")],
        };
        let obs = ObservedInput {
            observed_edges: vec![edge("a", "b"), edge("a", "c")],
            ..Default::default()
        };
        let inv = correlate(
            &[
                present_agent("a", "a-bot", &["read_repo"]),
                present_agent("b", "b-bot", &["read_repo"]),
            ],
            &declared,
            Some(&obs),
        );
        assert_eq!(inv.comm_graph.undeclared_edges, vec![edge("a", "c")]);
        assert_eq!(
            violations_of(&inv, "a"),
            vec![Violation::UndeclaredHandoff {
                from: "a".to_string(),
                to: "c".to_string(),
            }]
        );
    }

    #[test]
    fn declared_edge_also_observed_is_not_a_violation() {
        let declared = DeclaredGraph {
            edges: vec![edge("a", "b")],
        };
        let obs = ObservedInput {
            observed_edges: vec![edge("a", "b")],
            ..Default::default()
        };
        let inv = correlate(
            &[
                present_agent("a", "a-bot", &["read_repo"]),
                present_agent("b", "b-bot", &["read_repo"]),
            ],
            &declared,
            Some(&obs),
        );
        assert!(inv.comm_graph.undeclared_edges.is_empty());
        assert_eq!(inv.comm_graph.declared_edges, vec![edge("a", "b")]);
        assert_eq!(inv.comm_graph.observed_edges, vec![edge("a", "b")]);
        // Both ends of the observed declared edge were seen live with no
        // violation: they are Conform (not NotObserved).
        assert_eq!(inv.agents.len(), 2);
        for record in &inv.agents {
            assert_eq!(
                record.conformity,
                Conformity::Conform,
                "agent {}",
                record.agent_id
            );
        }
        assert_eq!(inv.summary.violation_count, 0);
    }

    #[test]
    fn output_is_sorted_by_agent_id() {
        let inv = correlate(
            &[
                present_agent("z-agent", "z-bot", &["read_repo"]),
                present_agent("a-agent", "a-bot", &["read_repo"]),
                shadow_agent("m-agent"),
            ],
            &DeclaredGraph::default(),
            None,
        );
        let ids: Vec<&str> = inv.agents.iter().map(|a| a.agent_id.as_str()).collect();
        assert_eq!(ids, vec!["a-agent", "m-agent", "z-agent"]);
    }

    #[test]
    fn runtime_recording_without_scanned_agent_synthesizes_shadow_record() {
        let mut rec = CaptureRecording::new("ghost");
        rec.observe(ObservationSurface::EbpfWire, "POST shadow-db:5432/w");
        let obs = ObservedInput {
            recordings: vec![rec],
            ..Default::default()
        };
        let inv = correlate(&[], &DeclaredGraph::default(), Some(&obs));
        assert_eq!(inv.agents.len(), 1);
        let record = &inv.agents[0];
        assert_eq!(record.agent_id, "ghost");
        assert_eq!(
            record.passport,
            PassportStatus::Absent {
                evidence: vec!["observed live (capture) with no source passport".to_string()],
            }
        );
        assert!(violations_of(&inv, "ghost").contains(&Violation::PassportAbsent));
        // The non-action key is egress evidence, never a violation.
        assert_eq!(
            record.observed.egress,
            vec!["POST shadow-db:5432/w".to_string()]
        );
        assert_eq!(inv.summary.without_passport, 1);
    }

    #[test]
    fn principal_mismatch_is_flagged() {
        let obs = ObservedInput {
            observed_principals: vec![("pr-bot".to_string(), "evil-bot".to_string())],
            ..Default::default()
        };
        let inv = correlate(
            &[present_agent("pr-bot", "good-bot", &["open_pr"])],
            &DeclaredGraph::default(),
            Some(&obs),
        );
        assert_eq!(
            violations_of(&inv, "pr-bot"),
            vec![Violation::PrincipalMismatch {
                declared: "good-bot".to_string(),
                observed: "evil-bot".to_string(),
            }]
        );
    }

    #[test]
    fn two_recordings_for_the_same_agent_accumulate() {
        let mut rec_a = CaptureRecording::new("pr-bot");
        rec_a.observe(ObservationSurface::HookSdk, "open_pr:acme/web#1");
        rec_a.observe(ObservationSurface::EbpfWire, "POST api.github.com:443/p");
        let mut rec_b = CaptureRecording::new("pr-bot");
        rec_b.observe(ObservationSurface::HookMcp, "read_repo:acme/web");
        // Same egress key as rec_a: must dedup, not duplicate.
        rec_b.observe(ObservationSurface::EbpfWire, "POST api.github.com:443/p");
        let obs = ObservedInput {
            recordings: vec![rec_a, rec_b],
            ..Default::default()
        };
        let inv = correlate(
            &[present_agent(
                "pr-bot",
                "good-bot",
                &["open_pr", "read_repo"],
            )],
            &DeclaredGraph::default(),
            Some(&obs),
        );
        // Both recordings accumulate onto ONE record, merged and deduped.
        assert_eq!(inv.agents.len(), 1);
        let record = &inv.agents[0];
        assert_eq!(
            record.observed.actions,
            vec!["open_pr".to_string(), "read_repo".to_string()]
        );
        assert_eq!(
            record.observed.egress,
            vec!["POST api.github.com:443/p".to_string()]
        );
        assert_eq!(record.conformity, Conformity::Conform);
    }

    #[test]
    fn observed_principal_for_unknown_agent_is_counted_but_synthesizes_no_record() {
        // Intentional asymmetry (module doc, rule 4): a recording proves a
        // live agent and synthesizes a shadow record; a bare observed
        // principal (or edge) matching no record synthesizes NOTHING and
        // raises no violation.
        let obs = ObservedInput {
            observed_principals: vec![("ghost".to_string(), "someone".to_string())],
            ..Default::default()
        };
        let inv = correlate(&[], &DeclaredGraph::default(), Some(&obs));
        assert!(inv.agents.is_empty());
        assert_eq!(inv.summary.violation_count, 0);
    }

    #[test]
    fn in_scope_action_and_egress_key_yield_conform() {
        let mut rec = CaptureRecording::new("pr-bot");
        rec.observe(ObservationSurface::HookSdk, "open_pr:acme/web#42");
        rec.observe(ObservationSurface::EbpfWire, "POST api.github.com:443/p");
        let obs = ObservedInput {
            recordings: vec![rec],
            ..Default::default()
        };
        let inv = correlate(
            &[present_agent(
                "pr-bot",
                "good-bot",
                &["open_pr", "read_repo"],
            )],
            &DeclaredGraph::default(),
            Some(&obs),
        );
        let record = &inv.agents[0];
        assert_eq!(record.conformity, Conformity::Conform);
        assert_eq!(record.observed.actions, vec!["open_pr".to_string()]);
        assert_eq!(
            record.observed.egress,
            vec!["POST api.github.com:443/p".to_string()]
        );
    }

    #[test]
    fn invalid_passport_stays_invalid_and_not_observed() {
        let scanned = ScannedAgent {
            root: "/scan/broken-agent".to_string(),
            passport: PassportStatus::Invalid {
                errors: vec!["agent.name is missing or empty".to_string()],
            },
        };
        let inv = correlate(&[scanned], &DeclaredGraph::default(), None);
        assert_eq!(inv.agents.len(), 1);
        // agent_id derived from the last path component of the scanned root.
        assert_eq!(inv.agents[0].agent_id, "broken-agent");
        // Invalid stays the signal; static-only adds no violation on top.
        assert_eq!(inv.agents[0].conformity, Conformity::NotObserved);
        assert_eq!(inv.summary.invalid_passport, 1);
        assert_eq!(inv.summary.violation_count, 0);
    }

    #[test]
    fn invalid_passport_observed_live_is_never_conform() {
        let scanned = vec![
            present_agent("pr-bot", "good-bot", &["open_pr"]),
            ScannedAgent {
                root: "/scan/broken-agent".to_string(),
                passport: PassportStatus::Invalid {
                    errors: vec!["agent.name is missing or empty".to_string()],
                },
            },
        ];
        let mut broken_rec = CaptureRecording::new("broken-agent");
        broken_rec.observe(ObservationSurface::EbpfWire, "POST api.github.com:443/x");
        let mut valid_rec = CaptureRecording::new("pr-bot");
        valid_rec.observe(ObservationSurface::HookSdk, "open_pr:acme/web#1");
        let obs = ObservedInput {
            recordings: vec![broken_rec, valid_rec],
            ..Default::default()
        };
        let inv = correlate(&scanned, &DeclaredGraph::default(), Some(&obs));
        assert_eq!(inv.agents.len(), 2);
        let broken = inv
            .agents
            .iter()
            .find(|a| a.agent_id == "broken-agent")
            .expect("broken record");
        // Observed live with egress evidence, but no parseable declaration:
        // never Conform (fail-safe -- a broken manifest must not outrank a
        // missing or a valid one).
        assert_eq!(broken.conformity, Conformity::NotObserved);
        assert_eq!(
            broken.observed.egress,
            vec!["POST api.github.com:443/x".to_string()]
        );
        // Discriminator: a sibling VALID record in the SAME run CAN be
        // Conform, so the gate targets the missing declaration only.
        let valid = inv
            .agents
            .iter()
            .find(|a| a.agent_id == "pr-bot")
            .expect("valid record");
        assert_eq!(valid.conformity, Conformity::Conform);
    }

    #[test]
    fn declared_graph_is_renormalized_on_intake() {
        // graph.rs exposes `edges` pub: feed an unsorted, duplicated set and
        // assert the correlator normalizes defensively.
        let declared = DeclaredGraph {
            edges: vec![edge("b", "a"), edge("a", "b"), edge("a", "b")],
        };
        let inv = correlate(&[], &declared, None);
        assert_eq!(
            inv.comm_graph.declared_edges,
            vec![edge("a", "b"), edge("b", "a")]
        );
    }

    #[test]
    fn repo_passport_record_keys_on_principal_when_no_agent_id() {
        // Real corpus repo passport: the repo shape has no agent_id, so the
        // record keys on the declared principal.
        let scanned = scan_tree(&corpus_path("repos/gh-pr-bot/repo")).expect("scan");
        let inv = correlate(&scanned, &DeclaredGraph::default(), None);
        assert_eq!(inv.agents.len(), 1);
        assert_eq!(inv.agents[0].agent_id, "acme-dependency-pr-bot[bot]");
        let declared = inv.agents[0].declared.as_ref().expect("declared");
        assert_eq!(declared.principal, "acme-dependency-pr-bot[bot]");
        assert_eq!(declared.target_systems, vec!["github".to_string()]);
        assert_eq!(
            declared.actions,
            vec!["open_pr".to_string(), "read_repo".to_string()]
        );
        assert_eq!(inv.agents[0].kind.as_deref(), Some("git_agent"));
    }

    #[test]
    fn correlate_is_deterministic_and_byte_stable() {
        let scanned = vec![
            present_agent("pr-bot", "good-bot", &["open_pr"]),
            shadow_agent("ghost"),
        ];
        let declared = DeclaredGraph {
            edges: vec![edge("pr-bot", "ghost")],
        };
        let mut rec = CaptureRecording::new("pr-bot");
        rec.observe(ObservationSurface::HookSdk, "push:acme/web");
        rec.observe(ObservationSurface::EbpfWire, "POST api.github.com:443/p");
        let obs = ObservedInput {
            recordings: vec![rec],
            observed_edges: vec![edge("ghost", "pr-bot")],
            observed_principals: vec![("pr-bot".to_string(), "evil-bot".to_string())],
        };
        let run_a = correlate(&scanned, &declared, Some(&obs));
        let run_b = correlate(&scanned, &declared, Some(&obs));
        // Not a vacuous pass: the run must carry the correlated content.
        assert_eq!(run_a.agents.len(), 2);
        assert_eq!(
            run_a.comm_graph.undeclared_edges,
            vec![edge("ghost", "pr-bot")]
        );
        assert_eq!(run_a, run_b);
        let json_a = serde_json::to_string(&run_a).expect("serialize");
        let json_b = serde_json::to_string(&run_b).expect("serialize");
        assert_eq!(json_a, json_b);
        // Bridge contract: uniform kind-tagged JSON -- every enum value is
        // an object with a "kind" key (Violation, Conformity, PassportStatus).
        assert!(json_a.contains(r#""kind":"undeclared_action""#), "{json_a}");
        assert!(json_a.contains(r#""kind":"violations""#), "{json_a}");
        assert!(json_a.contains(r#""kind":"present""#), "{json_a}");
        assert!(json_a.contains(r#""kind":"absent""#), "{json_a}");
    }
}
