//! Pure mapping: captured exec events -> per-agent surface recordings.
//!
//! This is the deterministic half of the probe (I4). The live capture
//! ([`crate::probe`]) is non-deterministic by nature (syscall timing); freezing
//! its output through this pure function yields a replay-stable
//! [`CaptureRecording`] the Python surface judge can consume.

use discoveryprobe_common::{ConnectEvent, ExecEvent};
use discoveryprobe_core::{CaptureRecording, ObservationSurface};

/// What the broker launched: an agent and the process command name the kernel
/// will report for it. `comm_marker` must be <= 15 bytes (the kernel truncates
/// `comm` to `TASK_COMM_LEN`); a longer marker can never match.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AgentProcessSpec {
    /// The simulated agent's identifier (matches `corpus/surface/<id>`).
    pub agent_id: String,
    /// The exact process command name expected for this agent.
    pub comm_marker: String,
}

impl AgentProcessSpec {
    /// Build a spec from an agent id and its expected process command name.
    pub fn new(agent_id: impl Into<String>, comm_marker: impl Into<String>) -> Self {
        Self {
            agent_id: agent_id.into(),
            comm_marker: comm_marker.into(),
        }
    }
}

/// Format a captured connect destination as `a.b.c.d:port` (userspace side, so
/// allocation is fine -- the alloc-free `ConnectEvent` only exposes the octets).
fn dest_of(event: &ConnectEvent) -> String {
    let o = event.octets();
    format!("{}.{}.{}.{}:{}", o[0], o[1], o[2], o[3], event.port())
}

/// Build one [`CaptureRecording`] per agent from the captured exec events.
///
/// Thin wrapper over [`recordings_from_capture`] with no connect events, kept
/// for callers that only observe process execs.
pub fn recordings_from_execs(
    agents: &[AgentProcessSpec],
    events: &[ExecEvent],
) -> Vec<CaptureRecording> {
    recordings_from_capture(agents, events, &[])
}

/// Build one [`CaptureRecording`] per agent from BOTH captured surfaces of the
/// kernel probe: process execs and outbound connects.
///
/// An agent is visible on the eBPF-wire surface iff a captured event's `comm`
/// equals its marker -- the kernel saw the agent run (`exec:comm:pid`) or dial
/// out (`connect:a.b.c.d:port`), even inside a container, WITHOUT any in-process
/// hook. The connect surface is what catches an LLM agent's provider egress
/// (agentwatch's httpcore view, here at the kernel). An agent with no matching
/// event gets an empty recording: detected nowhere (the ghost case the surface
/// recette must surface as a red gate).
///
/// Pure and deterministic: each recording is normalised (sorted, de-duplicated),
/// so the same captures serialise byte-for-byte identically (I4).
pub fn recordings_from_capture(
    agents: &[AgentProcessSpec],
    execs: &[ExecEvent],
    connects: &[ConnectEvent],
) -> Vec<CaptureRecording> {
    agents
        .iter()
        .map(|spec| {
            let mut recording = CaptureRecording::new(&spec.agent_id);
            for event in execs {
                let comm = event.comm_str();
                if comm == spec.comm_marker {
                    recording.observe(
                        ObservationSurface::EbpfWire,
                        format!("exec:{comm}:{}", event.pid),
                    );
                }
            }
            for event in connects {
                if event.comm_str() == spec.comm_marker {
                    recording.observe(
                        ObservationSurface::EbpfWire,
                        format!("connect:{}", dest_of(event)),
                    );
                }
            }
            recording.normalise();
            recording
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn exec(pid: u32, name: &str) -> ExecEvent {
        let mut comm = [0u8; discoveryprobe_common::COMM_LEN];
        let bytes = name.as_bytes();
        let n = bytes.len().min(discoveryprobe_common::COMM_LEN);
        comm[..n].copy_from_slice(&bytes[..n]);
        ExecEvent { pid, comm }
    }

    fn connect(pid: u32, daddr: [u8; 4], port: u16, name: &str) -> ConnectEvent {
        let mut comm = [0u8; discoveryprobe_common::COMM_LEN];
        let bytes = name.as_bytes();
        let n = bytes.len().min(discoveryprobe_common::COMM_LEN);
        comm[..n].copy_from_slice(&bytes[..n]);
        ConnectEvent {
            pid,
            daddr,
            dport: port.to_be_bytes(),
            _pad: [0u8; 2],
            comm,
        }
    }

    #[test]
    fn matching_exec_makes_agent_visible_on_ebpf_wire() {
        let agents = [AgentProcessSpec::new("pr-bot-sdk", "pr-bot")];
        let recs = recordings_from_execs(&agents, &[exec(42, "pr-bot")]);
        assert_eq!(recs.len(), 1);
        let visible = recs[0].surfaces.get(&ObservationSurface::EbpfWire);
        assert_eq!(visible, Some(&vec!["exec:pr-bot:42".to_string()]));
    }

    #[test]
    fn agent_with_no_matching_exec_is_detected_nowhere() {
        let agents = [AgentProcessSpec::new("ghost", "ghost-proc")];
        let recs = recordings_from_execs(&agents, &[exec(7, "other")]);
        assert!(!recs[0].detected_anywhere());
    }

    #[test]
    fn observations_are_sorted_and_deduplicated() {
        let agents = [AgentProcessSpec::new("a", "agent")];
        let events = [exec(9, "agent"), exec(2, "agent"), exec(9, "agent")];
        let recs = recordings_from_execs(&agents, &events);
        let visible = recs[0].surfaces.get(&ObservationSurface::EbpfWire).unwrap();
        // pid 9 deduped, sorted ascending by string: "...:2" before "...:9".
        assert_eq!(
            visible,
            &vec!["exec:agent:2".to_string(), "exec:agent:9".to_string()]
        );
    }

    #[test]
    fn matching_connect_makes_agent_visible_with_dest() {
        let agents = [AgentProcessSpec::new("llm-bot-sdk", "llm-bot")];
        let connects = [connect(42, [140, 82, 112, 3], 443, "llm-bot")];
        let recs = recordings_from_capture(&agents, &[], &connects);
        let visible = recs[0].surfaces.get(&ObservationSurface::EbpfWire);
        assert_eq!(visible, Some(&vec!["connect:140.82.112.3:443".to_string()]));
    }

    #[test]
    fn exec_and_connect_reconcile_on_one_ebpf_wire_surface() {
        let agents = [AgentProcessSpec::new("a", "llm-bot")];
        let recs = recordings_from_capture(
            &agents,
            &[exec(7, "llm-bot")],
            &[connect(7, [1, 1, 1, 1], 443, "llm-bot")],
        );
        let visible = recs[0].surfaces.get(&ObservationSurface::EbpfWire).unwrap();
        // Both surfaces of the kernel probe land on ebpf_wire, sorted.
        assert_eq!(
            visible,
            &vec![
                "connect:1.1.1.1:443".to_string(),
                "exec:llm-bot:7".to_string()
            ]
        );
    }

    #[test]
    fn connect_from_another_process_does_not_attach_to_agent() {
        let agents = [AgentProcessSpec::new("ghost", "ghost-proc")];
        let recs = recordings_from_capture(&agents, &[], &[connect(9, [8, 8, 8, 8], 53, "curl")]);
        assert!(!recs[0].detected_anywhere());
    }
}
