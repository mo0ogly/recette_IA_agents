//! Inventory report: serializable output of the scan, conformity, and graph results.
//!
//! `to_json` is a thin serializer over `model::AgentInventory`: it adds NO
//! ordering logic. Byte-identical output for identical inputs (I4) follows
//! from (a) the correlator pre-sorting every list (agents, violations, edges,
//! evidence) and (b) serde emitting struct fields in declaration order.
//!
//! Output format: COMPACT `serde_json::to_string` (not pretty). The consumers
//! are files and the Python bridge, not a terminal: compact is byte-stable
//! like pretty but smaller, and any presentation layer can re-indent.

use crate::model::AgentInventory;
use std::fmt;

/// Error serializing an inventory report.
#[derive(Debug)]
pub enum ReportError {
    /// JSON serialization failed; carries the underlying serde_json error.
    Serialize(serde_json::Error),
}

impl fmt::Display for ReportError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ReportError::Serialize(e) => write!(f, "cannot serialize inventory: {e}"),
        }
    }
}

impl std::error::Error for ReportError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            ReportError::Serialize(e) => Some(e),
        }
    }
}

/// Serializes the inventory to compact JSON. Deterministic (I4): the struct
/// is pre-sorted by `correlate`, so the same inventory always yields the
/// same bytes; this function adds no ordering of its own.
pub fn to_json(inventory: &AgentInventory) -> Result<String, ReportError> {
    serde_json::to_string(inventory).map_err(ReportError::Serialize)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::correlate::correlate;
    use crate::graph::DeclaredGraph;
    use crate::model::AgentInventory;
    use crate::scan::scan_tree;
    use crate::test_support::{corpus_path, fixture_path};
    use std::path::Path;

    /// The full static pipeline: scan one tree, correlate static-only,
    /// serialize. Two invocations on the same tree must be byte-identical.
    fn run_full(root: &Path) -> String {
        let scanned = scan_tree(root).expect("scan");
        let inventory = correlate(&scanned, &DeclaredGraph::default(), None);
        to_json(&inventory).expect("serialize")
    }

    #[test]
    fn inventory_json_is_byte_identical_across_two_runs_on_the_same_inputs() {
        let a = run_full(&corpus_path("repos/gh-pr-bot/repo"));
        let b = run_full(&corpus_path("repos/gh-pr-bot/repo"));
        // Byte-identical JSON across two full runs on the same inputs (I4).
        assert_eq!(a, b);
        // Guard against a vacuous pass: the run carries the corpus content.
        assert!(a.contains("acme-dependency-pr-bot"), "{a}");
    }

    /// Builds a structurally rich inventory: two scanned trees (one Present
    /// passport, one shadow agent) plus a declared graph from a real
    /// orchestration team.json -- enough structure that byte-stability is
    /// non-trivial (multiple sorted lists, edges, violations).
    fn build_structured() -> (AgentInventory, String) {
        let mut scanned = scan_tree(&corpus_path("repos/gh-pr-bot/repo")).expect("scan pr-bot");
        scanned.extend(scan_tree(&fixture_path("shadow-agent")).expect("scan shadow-agent"));
        let raw = std::fs::read_to_string(corpus_path(
            "maf_orchestration/correct/finance-approval-handoff-correct/team.json",
        ))
        .expect("read team.json");
        let graph = DeclaredGraph::from_team_json(&raw).expect("team graph");
        let inventory = correlate(&scanned, &graph, None);
        let json = to_json(&inventory).expect("serialize");
        (inventory, json)
    }

    #[test]
    fn structured_inventory_json_is_byte_identical_and_round_trips() {
        let (inventory_a, json_a) = build_structured();
        let (_inventory_b, json_b) = build_structured();
        // Byte-identical JSON across two full runs on the same inputs (I4).
        assert_eq!(json_a, json_b);
        // Not vacuous: passport record + shadow record, and the 4 declared
        // handoff edges of the finance team.json.
        assert_eq!(inventory_a.agents.len(), 2);
        assert_eq!(inventory_a.comm_graph.declared_edges.len(), 4);
        assert_eq!(inventory_a.summary.with_passport, 1);
        assert_eq!(inventory_a.summary.without_passport, 1);
        // The JSON round-trips back to the exact same struct.
        let parsed: AgentInventory = serde_json::from_str(&json_a).expect("round-trip parse");
        assert_eq!(parsed, inventory_a);
    }
}
