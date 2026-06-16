//! Emit a hook_sdk CaptureRecording (from captured traces) as the JSON the Python
//! surface judge consumes -- the cross-language bridge proof. Run:
//!   cargo run -p discoveryprobe-capture --example emit_recording
//! then pipe into: python -m recette surface --recording <file>

use discoveryprobe_capture::{recording_from_traces, LlmCallTrace};

fn trace(seq: u64, kind: &str, tool: Option<&str>, resource: &str) -> LlmCallTrace {
    LlmCallTrace {
        seq,
        event_id: format!("LC{seq:06}"),
        agent_id: "demo-gh-bot".to_string(),
        model: "llama-3.3-70b-versatile".to_string(),
        kind: kind.to_string(),
        tool_name: tool.map(str::to_string),
        resource: resource.to_string(),
        prompt_tokens: 0,
        completion_tokens: 0,
        latency_ms: 0,
        error: None,
    }
}

fn main() {
    let traces = [
        trace(1, "tool_call", Some("read_repo"), "acme/x"),
        trace(2, "tool_call", Some("open_pr"), "acme/x"),
        trace(3, "final", None, ""),
    ];
    let recording = recording_from_traces("demo-gh-bot", &traces);
    // A bare recordings list -- the shape `score_recording` accepts.
    let json = recording.to_json().expect("serialise recording");
    println!("[{json}]");
}
