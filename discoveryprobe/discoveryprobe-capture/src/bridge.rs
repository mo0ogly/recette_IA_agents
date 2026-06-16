//! Bridge captured traces -> the hook surface recording.
//!
//! Mirrors the Python `recette/capture/surface_bridge.py`: a run's tool-call
//! intents become `hook_sdk` observations in a `discoveryprobe_core`
//! [`CaptureRecording`], scored by the SAME surface judge as the eBPF wire
//! surface (one model, reconciled). Only tool calls are observable -- a pure
//! thought/final reveals no action. Deterministic: a pure function of the traces.

use discoveryprobe_core::{CaptureRecording, ObservationSurface};

use crate::LlmCallTrace;

/// Build a `hook_sdk` [`CaptureRecording`] from captured tool-call intents.
pub fn recording_from_traces(agent_id: &str, traces: &[LlmCallTrace]) -> CaptureRecording {
    let mut recording = CaptureRecording::new(agent_id);
    for trace in traces {
        if trace.is_tool_call() && trace.tool_name.is_some() {
            recording.observe(ObservationSurface::HookSdk, trace.intent());
        }
    }
    recording.normalise();
    recording
}

#[cfg(test)]
mod tests {
    use super::*;

    fn trace(seq: u64, kind: &str, tool: Option<&str>, resource: &str) -> LlmCallTrace {
        LlmCallTrace {
            seq,
            event_id: format!("LC{seq:06}"),
            agent_id: "a1".to_string(),
            model: "m".to_string(),
            kind: kind.to_string(),
            tool_name: tool.map(str::to_string),
            resource: resource.to_string(),
            prompt_tokens: 0,
            completion_tokens: 0,
            latency_ms: 9,
            error: None,
        }
    }

    #[test]
    fn tool_calls_become_hook_sdk_visible() {
        let recording =
            recording_from_traces("a1", &[trace(1, "tool_call", Some("read_repo"), "acme/x")]);
        assert_eq!(
            recording.surfaces.get(&ObservationSurface::HookSdk),
            Some(&vec!["read_repo:acme/x".to_string()])
        );
    }

    #[test]
    fn final_only_run_is_blind_on_hook() {
        let recording = recording_from_traces("ghost", &[trace(1, "final", None, "")]);
        assert!(!recording
            .surfaces
            .contains_key(&ObservationSurface::HookSdk));
    }

    #[test]
    fn intents_sorted_and_deduplicated() {
        let recording = recording_from_traces(
            "a1",
            &[
                trace(1, "tool_call", Some("open_pr"), "acme/x"),
                trace(2, "tool_call", Some("read_repo"), "acme/x"),
                trace(3, "tool_call", Some("open_pr"), "acme/x"),
            ],
        );
        assert_eq!(
            recording.surfaces.get(&ObservationSurface::HookSdk),
            Some(&vec![
                "open_pr:acme/x".to_string(),
                "read_repo:acme/x".to_string()
            ])
        );
    }
}
