//! The declared-agents manifest: the broker's allowlist.
//!
//! Deny-by-default (failure-modes.md): a capture request may only name agents
//! that appear here, each mapped to the process command name the kernel reports
//! for it. The manifest also caps the capture window. recette.sh hands the
//! broker this manifest path (R19); it is the bench's declared corpus, never a
//! free-form argument from the caller.

use std::collections::BTreeMap;
use std::path::Path;

use serde::Deserialize;

/// One declared agent: the process command name (`comm`, <= 15 bytes) the eBPF
/// capture expects to see for it.
#[derive(Debug, Clone, Deserialize)]
pub struct AgentEntry {
    /// The exact process command name the kernel reports for this agent.
    pub comm_marker: String,
}

/// The broker allowlist + capture bound.
#[derive(Debug, Clone, Deserialize)]
pub struct Manifest {
    /// Hard ceiling on a capture window (ms); a request above this is rejected.
    pub max_duration_ms: u64,
    /// Declared agents, keyed by agent id (sorted, deterministic iteration).
    pub agents: BTreeMap<String, AgentEntry>,
}

impl Manifest {
    /// Parse a manifest from JSON.
    pub fn from_json(raw: &str) -> Result<Self, serde_json::Error> {
        serde_json::from_str(raw)
    }

    /// Load a manifest from a file path.
    pub fn load(path: impl AsRef<Path>) -> anyhow::Result<Self> {
        let raw = std::fs::read_to_string(path.as_ref())?;
        Ok(Self::from_json(&raw)?)
    }

    /// The declared process marker for `agent_id`, or `None` if undeclared
    /// (deny-by-default: an undeclared agent has no marker and is rejected).
    pub fn marker(&self, agent_id: &str) -> Option<&str> {
        self.agents.get(agent_id).map(|e| e.comm_marker.as_str())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn manifest() -> Manifest {
        Manifest::from_json(
            r#"{
                "max_duration_ms": 5000,
                "agents": {
                    "pr-bot-sdk": {"comm_marker": "pr-bot"},
                    "ghost-direct-db": {"comm_marker": "ghost-proc"}
                }
            }"#,
        )
        .expect("parse")
    }

    #[test]
    fn marker_resolves_declared_agent() {
        assert_eq!(manifest().marker("pr-bot-sdk"), Some("pr-bot"));
    }

    #[test]
    fn marker_is_none_for_undeclared_agent() {
        assert_eq!(manifest().marker("intruder"), None);
    }
}
