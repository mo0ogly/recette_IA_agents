//! Multi-agent communication graph built from declared handoffs and endpoints.
//!
//! Two declaration sources feed the DECLARED graph:
//!
//! - an orchestration `team.json` (`corpus/schemas/maf-orchestration.schema.json`):
//!   for the `handoff` style, each participant's `handoffs` set declares the
//!   allowed (from, to) edges (the HandoffBuilder per-source
//!   `HandoffConfiguration` set). The other styles (`sequential`, `concurrent`,
//!   `group_chat`, `magentic`) declare no handoff mesh, so they yield an
//!   EMPTY graph -- a valid declaration, never an error;
//! - an agent passport (`manifest::Passport`): a `maf_agent` may declare
//!   `{"action": "handoff", "target": ...}` capabilities; each target is an
//!   edge from that agent.
//!
//! The declared graph is one half of undeclared-communication detection: the
//! correlator diffs OBSERVED edges (runtime IPC capture) against these
//! DECLARED edges; an observed edge absent here is a violation.
//!
//! Determinism (I4): edges are ALWAYS sorted and deduplicated, in every
//! constructor and after every merge, so the graph is byte-stable regardless
//! of source ordering.
//!
//! Failure mode (fail-safe): a team.json that does not parse against the
//! orchestration shape is a `GraphError` carrying the serde message -- never
//! a silent empty graph.

use crate::manifest::Passport;
use serde::{Deserialize, Serialize};
use std::fmt;

/// Error building a declared graph from a team.json document.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum GraphError {
    /// The team.json document does not parse against the orchestration
    /// shape; carries the serde error message.
    InvalidTeamJson(String),
}

impl fmt::Display for GraphError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            GraphError::InvalidTeamJson(e) => write!(f, "invalid team.json: {e}"),
        }
    }
}

impl std::error::Error for GraphError {}

/// One declared directed communication edge: `from` may hand off to `to`.
#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
pub struct Edge {
    /// Source participant / agent id.
    pub from: String,
    /// Target participant / agent id.
    pub to: String,
}

/// The declared handoff graph. `edges` is always sorted and deduplicated.
#[derive(Debug, Clone, PartialEq, Default, Serialize, Deserialize)]
pub struct DeclaredGraph {
    /// Declared directed edges, sorted and deduplicated (I4-stable).
    pub edges: Vec<Edge>,
}

// ---------------------------------------------------------------------------
// team.json shape (verified against corpus/schemas/maf-orchestration.schema.json
// and corpus/maf_orchestration/correct/finance-approval-handoff-correct/team.json)
// ---------------------------------------------------------------------------

/// The subset of the orchestration team.json the graph needs. Field names
/// trace to maf-orchestration.schema.json: `style` (enum, schema default
/// "handoff"), `participants` (required), participant `agent_id` (required)
/// and `handoffs[].target` (required per handoff item).
#[derive(Debug, Deserialize)]
struct TeamDoc {
    /// Orchestration style; absent means "handoff" (the schema default).
    style: Option<String>,
    /// The mesh participants (required by the schema).
    participants: Vec<TeamParticipant>,
}

/// One participant of the team.json `participants` array.
#[derive(Debug, Deserialize)]
struct TeamParticipant {
    /// Participant id (required by the schema).
    agent_id: String,
    /// Allowed handoff targets for this participant (optional: a participant
    /// may declare none, e.g. every participant of a concurrent team).
    handoffs: Option<Vec<TeamHandoff>>,
}

/// One entry of a participant's `handoffs` set.
#[derive(Debug, Deserialize)]
struct TeamHandoff {
    /// Target participant id (required by the schema).
    target: String,
}

impl DeclaredGraph {
    /// Builds the declared graph from raw team.json content.
    ///
    /// `handoff` style (explicit, or absent per the schema default): each
    /// participant's `handoffs` set yields (participant, target) edges. Any
    /// other style (`sequential`, `concurrent`, `group_chat`, `magentic`)
    /// declares no handoff mesh and yields an EMPTY graph, not an error.
    /// A document that does not parse is a `GraphError::InvalidTeamJson`.
    pub fn from_team_json(raw: &str) -> Result<DeclaredGraph, GraphError> {
        let doc: TeamDoc =
            serde_json::from_str(raw).map_err(|e| GraphError::InvalidTeamJson(e.to_string()))?;
        // The schema defaults an absent style to "handoff".
        let style = doc.style.as_deref().unwrap_or("handoff");
        if style != "handoff" {
            return Ok(DeclaredGraph::default());
        }
        let edges = doc
            .participants
            .iter()
            .flat_map(|p| {
                p.handoffs.iter().flatten().map(|h| Edge {
                    from: p.agent_id.clone(),
                    to: h.target.clone(),
                })
            })
            .collect();
        Ok(DeclaredGraph::from_edges(edges))
    }

    /// Builds the declared graph from an agent passport: one edge per declared
    /// handoff capability, sourced at the passport's `agent_id`. The repo
    /// shape carries no `agent_id`, so the declared `principal` stands in as
    /// the source node (documented choice: it is the only stable declared
    /// identifier there; today the repo shape also declares no handoffs, so
    /// that arm is a defensive fallback, not a live path).
    pub fn from_passport(passport: &Passport) -> DeclaredGraph {
        let from = match passport.agent_id() {
            Some(id) => id.to_string(),
            None => passport.principal(),
        };
        let edges = passport
            .handoffs()
            .into_iter()
            .map(|to| Edge {
                from: from.clone(),
                to,
            })
            .collect();
        DeclaredGraph::from_edges(edges)
    }

    /// Unions this graph with another, deterministically: the result is the
    /// sorted, deduplicated union of both edge sets. The correlator uses this
    /// to combine N passports + M team files into one declared graph.
    pub fn merge(mut self, other: DeclaredGraph) -> DeclaredGraph {
        self.edges.extend(other.edges);
        DeclaredGraph::from_edges(self.edges)
    }

    /// Normalizing constructor: sorts and deduplicates, upholding the
    /// invariant that `edges` is always sorted unique (I4).
    fn from_edges(mut edges: Vec<Edge>) -> DeclaredGraph {
        edges.sort();
        edges.dedup();
        DeclaredGraph { edges }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::test_support::corpus_path;

    /// Shorthand edge constructor for assertions.
    fn edge(from: &str, to: &str) -> Edge {
        Edge {
            from: from.to_string(),
            to: to.to_string(),
        }
    }

    #[test]
    fn handoff_team_json_yields_the_declared_edges() {
        let raw = std::fs::read_to_string(corpus_path(
            "maf_orchestration/correct/finance-approval-handoff-correct/team.json",
        ))
        .expect("read");
        let graph = DeclaredGraph::from_team_json(&raw).expect("valid team.json");
        // Exactly the (from, to) pairs declared in the file, sorted (I4):
        // intake -> wire, intake -> audit, wire -> intake, audit -> intake.
        assert_eq!(
            graph.edges,
            vec![
                edge("audit", "intake"),
                edge("intake", "audit"),
                edge("intake", "wire"),
                edge("wire", "intake"),
            ]
        );
    }

    #[test]
    fn team_without_handoffs_yields_no_edges() {
        // style "concurrent", no handoff config anywhere -- valid, empty graph.
        let raw = std::fs::read_to_string(corpus_path(
            "maf_orchestration/correct/concurrent-review-correct/team.json",
        ))
        .expect("read");
        let graph = DeclaredGraph::from_team_json(&raw).expect("valid team.json");
        assert!(
            graph.edges.is_empty(),
            "unexpected edges: {:?}",
            graph.edges
        );
    }

    #[test]
    fn passport_handoff_capability_yields_self_edge() {
        // Real MAF fixture: diagnostic-correct declares one handoff capability
        // {"action": "handoff", "target": "remediation-agent"}.
        let raw = std::fs::read_to_string(corpus_path(
            "maf_agents/correct/diagnostic-correct/spec.json",
        ))
        .expect("read");
        let passport = Passport::parse(&raw).expect("valid passport");
        let graph = DeclaredGraph::from_passport(&passport);
        assert_eq!(
            graph.edges,
            vec![edge("diagnostic-correct", "remediation-agent")]
        );
    }

    #[test]
    fn passport_without_handoffs_yields_empty_graph() {
        // Git agent: no handoff capabilities at all.
        let raw =
            std::fs::read_to_string(corpus_path("agents/correct/gh-issue-triager/manifest.json"))
                .expect("read");
        let passport = Passport::parse(&raw).expect("valid passport");
        let graph = DeclaredGraph::from_passport(&passport);
        assert!(graph.edges.is_empty());
    }

    #[test]
    fn edges_are_sorted_and_deduplicated() {
        // Two sources with overlapping and unsorted edges.
        let a = DeclaredGraph {
            edges: vec![edge("b", "a"), edge("a", "b")],
        };
        let b = DeclaredGraph {
            edges: vec![edge("a", "b"), edge("a", "c")],
        };
        let merged = a.merge(b);
        assert_eq!(
            merged.edges,
            vec![edge("a", "b"), edge("a", "c"), edge("b", "a")]
        );
    }

    #[test]
    fn merge_with_empty_graph_is_identity_modulo_normalization() {
        let g = DeclaredGraph {
            edges: vec![edge("y", "z"), edge("x", "y")],
        };
        let merged = g.merge(DeclaredGraph::default());
        assert_eq!(merged.edges, vec![edge("x", "y"), edge("y", "z")]);
    }

    #[test]
    fn malformed_team_json_yields_graph_error_with_serde_message() {
        let err = DeclaredGraph::from_team_json("{not json").unwrap_err();
        assert!(matches!(err, GraphError::InvalidTeamJson(_)));
        assert!(
            err.to_string().starts_with("invalid team.json:"),
            "unexpected Display: {err}"
        );
        // Valid JSON missing the required `participants` array is also
        // malformed for the orchestration shape.
        let err = DeclaredGraph::from_team_json(r#"{"style": "handoff"}"#).unwrap_err();
        assert!(err.to_string().contains("participants"), "got: {err}");
    }
}
