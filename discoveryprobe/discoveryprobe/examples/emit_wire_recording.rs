//! Emit a reconciled `ebpf_wire` CaptureRecording (process exec + outbound
//! connect) as the JSON the Python surface judge consumes -- the GR4/GR5
//! cross-language bridge proof for the kernel-wire surface. Run:
//!   cargo run -p discoveryprobe --example emit_wire_recording
//! then pipe into: python -m recette surface --recording <file>
//!
//! This is exactly the shape the privileged broker emits, minus the kernel: the
//! pure mapping turns canned exec+connect events into the recording, so the
//! Rust capture and the Python judge agree without CAP_BPF.

use discoveryprobe::{recordings_from_capture, AgentProcessSpec};
use discoveryprobe_common::{ConnectEvent, ExecEvent};

fn exec(pid: u32, comm: &str) -> ExecEvent {
    let mut bytes = [0u8; discoveryprobe_common::COMM_LEN];
    let src = comm.as_bytes();
    let n = src.len().min(discoveryprobe_common::COMM_LEN);
    bytes[..n].copy_from_slice(&src[..n]);
    ExecEvent { pid, comm: bytes }
}

fn connect(pid: u32, daddr: [u8; 4], port: u16, comm: &str) -> ConnectEvent {
    let mut bytes = [0u8; discoveryprobe_common::COMM_LEN];
    let src = comm.as_bytes();
    let n = src.len().min(discoveryprobe_common::COMM_LEN);
    bytes[..n].copy_from_slice(&src[..n]);
    ConnectEvent {
        pid,
        daddr,
        dport: port.to_be_bytes(),
        _pad: [0u8; 2],
        comm: bytes,
    }
}

fn main() {
    let agents = [AgentProcessSpec::new("ghost-llm-bot", "llm-bot")];
    // The agent ran (exec) and dialed its LLM provider over HTTPS (connect) --
    // both caught on the wire WITHOUT an in-process hook (the ghost case).
    let execs = [exec(4242, "llm-bot")];
    let connects = [connect(4242, [140, 82, 112, 3], 443, "llm-bot")];
    let recordings = recordings_from_capture(&agents, &execs, &connects, &[], &[]);
    // Emit a JSON array of recordings (the shape `recette surface --recording`
    // accepts). Use each recording's own bridge serialiser -- no extra dep.
    let body = recordings
        .iter()
        .map(|r| r.to_json().expect("serialise recording"))
        .collect::<Vec<_>>()
        .join(",");
    println!("[{body}]");
}
