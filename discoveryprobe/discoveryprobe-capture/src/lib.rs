//! Agent-capture trace schema, migrated to Rust.
//!
//! The enriched per-call record adapts tensorstax/agenttrace's trace field set
//! (`TraceManager._log_trace_end(func_name, session_id, duration_ms, success)` ->
//! intent + agent + latency + error) and is JSON-compatible with the Python
//! bridge (`recette/capture/llm_trace.py::LlmCallTrace.to_dict`), so a Rust
//! wire/eBPF capture and the Python hook produce the same record.
//!
//! See `docs/migration-provenance.md` and NOTICE for upstream attribution.

#![deny(missing_docs)]

use serde::{Deserialize, Serialize};

/// One captured LLM decision: the agent's intent plus operational metrics.
///
/// `latency_ms` is wall-clock OPERATIONAL metadata and must never enter a
/// detection/judge path (the detection surface is derived from `intent` only).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct LlmCallTrace {
    /// Monotonic sequence within the captured run.
    pub seq: u64,
    /// Sequence-derived id (`LC{seq:06}`), no clock (replay-stable).
    pub event_id: String,
    /// The agent this decision belongs to.
    pub agent_id: String,
    /// The model that produced the decision.
    pub model: String,
    /// `"tool_call"` or `"final"`.
    pub kind: String,
    /// The tool invoked, when `kind == "tool_call"`.
    pub tool_name: Option<String>,
    /// The resource the tool acted on (empty for a final thought).
    pub resource: String,
    /// Prompt tokens reported by the provider.
    pub prompt_tokens: u64,
    /// Completion tokens reported by the provider.
    pub completion_tokens: u64,
    /// Measured latency in milliseconds (operational only).
    pub latency_ms: u64,
    /// The error, if the decision failed.
    pub error: Option<String>,
}

impl LlmCallTrace {
    /// The hook-surface key: `{tool_name}:{resource}` (empty tool -> `:`). Matches
    /// `recette/surface/surfaces.py::_hook_key` so a captured tool-call lines up
    /// with the hook surface.
    pub fn intent(&self) -> String {
        format!(
            "{}:{}",
            self.tool_name.as_deref().unwrap_or(""),
            self.resource
        )
    }

    /// Prompt + completion tokens.
    pub fn total_tokens(&self) -> u64 {
        self.prompt_tokens + self.completion_tokens
    }

    /// Whether this decision is an observable tool action (vs a pure thought).
    pub fn is_tool_call(&self) -> bool {
        self.kind == "tool_call"
    }

    /// Serialise to the JSON shape the Python bridge emits (adds the derived
    /// `intent` and `total_tokens` fields).
    pub fn to_json(&self) -> Result<String, serde_json::Error> {
        let value = serde_json::json!({
            "seq": self.seq,
            "event_id": self.event_id,
            "agent_id": self.agent_id,
            "model": self.model,
            "kind": self.kind,
            "tool_name": self.tool_name,
            "resource": self.resource,
            "intent": self.intent(),
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens(),
            "latency_ms": self.latency_ms,
            "error": self.error,
        });
        serde_json::to_string(&value)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tool_call() -> LlmCallTrace {
        LlmCallTrace {
            seq: 1,
            event_id: "LC000001".to_string(),
            agent_id: "a1".to_string(),
            model: "llama-3.3-70b-versatile".to_string(),
            kind: "tool_call".to_string(),
            tool_name: Some("read_repo".to_string()),
            resource: "acme/x".to_string(),
            prompt_tokens: 120,
            completion_tokens: 18,
            latency_ms: 842,
            error: None,
        }
    }

    #[test]
    fn intent_joins_tool_and_resource() {
        assert_eq!(tool_call().intent(), "read_repo:acme/x");
    }

    #[test]
    fn intent_of_a_final_thought_has_empty_tool() {
        let mut trace = tool_call();
        trace.kind = "final".to_string();
        trace.tool_name = None;
        trace.resource = String::new();
        assert_eq!(trace.intent(), ":");
    }

    #[test]
    fn total_tokens_sums_prompt_and_completion() {
        assert_eq!(tool_call().total_tokens(), 138);
    }

    #[test]
    fn to_json_carries_intent_and_total_tokens() {
        let json = tool_call().to_json().expect("serialise");
        assert!(json.contains("\"intent\":\"read_repo:acme/x\""));
        assert!(json.contains("\"total_tokens\":138"));
    }

    #[test]
    fn json_round_trips_through_the_struct() {
        let original = tool_call();
        let json = serde_json::to_string(&original).expect("ser");
        let back: LlmCallTrace = serde_json::from_str(&json).expect("de");
        assert_eq!(back, original);
    }
}
