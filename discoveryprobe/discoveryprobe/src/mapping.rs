//! Pure mapping: captured exec events -> per-agent surface recordings.
//!
//! This is the deterministic half of the probe (I4). The live capture
//! ([`crate::probe`]) is non-deterministic by nature (syscall timing); freezing
//! its output through this pure function yields a replay-stable
//! [`CaptureRecording`] the Python surface judge can consume.

use discoveryprobe_common::ExecEvent;
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

/// Build one [`CaptureRecording`] per agent from the captured exec events.
///
/// An agent is visible on the eBPF-wire surface iff a captured process `comm`
/// equals its marker -- the kernel saw the agent's process run, even inside a
/// container. An agent with no matching exec gets an empty recording: detected
/// nowhere (the ghost case the surface recette must surface as a red gate).
///
/// Pure and deterministic: each recording is normalised (sorted, de-duplicated),
/// so the same captures serialise byte-for-byte identically.
pub fn recordings_from_execs(
    agents: &[AgentProcessSpec],
    events: &[ExecEvent],
) -> Vec<CaptureRecording> {
    agents
        .iter()
        .map(|spec| {
            let mut recording = CaptureRecording::new(&spec.agent_id);
            for event in events {
                let comm = event.comm_str();
                if comm == spec.comm_marker {
                    recording.observe(
                        ObservationSurface::EbpfWire,
                        format!("exec:{comm}:{}", event.pid),
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
}
