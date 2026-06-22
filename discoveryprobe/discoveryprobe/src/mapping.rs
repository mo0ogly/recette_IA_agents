//! Pure mapping: captured exec events -> per-agent surface recordings.
//!
//! This is the deterministic half of the probe (I4). The live capture
//! ([`crate::probe`]) is non-deterministic by nature (syscall timing); freezing
//! its output through this pure function yields a replay-stable
//! [`CaptureRecording`] the Python surface judge can consume.

use std::collections::BTreeSet;

use discoveryprobe_common::{ConnectEvent, ExecEvent, ForkEvent};
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
    /// Optional exact pids of the agent's process(es). When the launcher knows
    /// the spawned child pid it matches PRECISELY by pid, sidestepping `comm`
    /// truncation (15 bytes) and collisions. Empty = match by `comm_marker` only.
    pub pids: Vec<u32>,
}

impl AgentProcessSpec {
    /// Build a spec matched by `comm_marker` only (no pid).
    pub fn new(agent_id: impl Into<String>, comm_marker: impl Into<String>) -> Self {
        Self {
            agent_id: agent_id.into(),
            comm_marker: comm_marker.into(),
            pids: Vec::new(),
        }
    }

    /// Build a spec that ALSO matches the given pids (precise attribution).
    pub fn with_pids(
        agent_id: impl Into<String>,
        comm_marker: impl Into<String>,
        pids: Vec<u32>,
    ) -> Self {
        Self {
            agent_id: agent_id.into(),
            comm_marker: comm_marker.into(),
            pids,
        }
    }

    /// True iff a captured event (its `comm` + `pid`) belongs to this agent:
    /// an exact pid match (precise) OR the comm marker (fallback).
    pub fn matches(&self, comm: &str, pid: u32) -> bool {
        self.pids.contains(&pid) || comm == self.comm_marker
    }
}

/// The transitive set of pids attributed to an agent: the seed pids plus every
/// process forked (directly or transitively) from a pid already in the set.
///
/// Pure fixpoint over the captured fork edges -- a child pid is added once its
/// parent is attributed, then iterated until no new pid appears. Only NEW pids
/// are added each pass, so a fork cycle (a pid graph that loops back) cannot
/// spin forever. Deterministic: the `BTreeSet` gives a stable iteration order so
/// the same captures attribute the same pids byte-for-byte (I4).
fn attributed_pids(seed: &[u32], forks: &[ForkEvent]) -> BTreeSet<u32> {
    let mut attributed: BTreeSet<u32> = seed.iter().copied().collect();
    loop {
        let mut added = false;
        for fork in forks {
            if attributed.contains(&fork.parent_pid) && attributed.insert(fork.child_pid) {
                added = true;
            }
        }
        if !added {
            break;
        }
    }
    attributed
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
    recordings_from_capture(agents, events, &[], &[])
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
/// Process-tree attribution: the `forks` edges let a child process's exec or
/// connect be attributed to the agent that owns the parent pid, so a
/// multi-process agent (a launcher that forks the real worker) is not a blind
/// spot. An event matches an agent when its `comm` is the marker OR its pid is
/// in the agent's transitively-attributed pid set (seed pids + fork descendants).
/// When `forks` is empty or the spec has no pids, attribution reduces to the
/// prior `comm`/pid match -- behaviour is unchanged.
///
/// Pure and deterministic: each recording is normalised (sorted, de-duplicated),
/// so the same captures serialise byte-for-byte identically (I4).
pub fn recordings_from_capture(
    agents: &[AgentProcessSpec],
    execs: &[ExecEvent],
    connects: &[ConnectEvent],
    forks: &[ForkEvent],
) -> Vec<CaptureRecording> {
    agents
        .iter()
        .map(|spec| {
            let attributed = attributed_pids(&spec.pids, forks);
            let mut recording = CaptureRecording::new(&spec.agent_id);
            for event in execs {
                let comm = event.comm_str();
                if spec.matches(comm, event.pid) || attributed.contains(&event.pid) {
                    recording.observe(
                        ObservationSurface::EbpfWire,
                        format!("exec:{comm}:{}", event.pid),
                    );
                }
            }
            for event in connects {
                if spec.matches(event.comm_str(), event.pid) || attributed.contains(&event.pid) {
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

    fn fork(parent: u32, child: u32) -> ForkEvent {
        ForkEvent {
            parent_pid: parent,
            child_pid: child,
        }
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
    fn pid_match_attributes_even_when_comm_differs() {
        // The launcher knows the spawned pid; match precisely by pid even though
        // the kernel comm ("python3") is not the agent id (comm fallback misses).
        let agents = [AgentProcessSpec::with_pids(
            "dx-live-bot",
            "dx-live-bot",
            vec![4242],
        )];
        let recs = recordings_from_capture(
            &agents,
            &[exec(4242, "python3")],
            &[connect(4242, [127, 0, 0, 1], 9101, "python3")],
            &[],
        );
        let visible = recs[0].surfaces.get(&ObservationSurface::EbpfWire).unwrap();
        assert!(visible.contains(&"exec:python3:4242".to_string()));
        assert!(visible.contains(&"connect:127.0.0.1:9101".to_string()));
    }

    #[test]
    fn pid_mismatch_with_wrong_comm_is_not_attributed() {
        let agents = [AgentProcessSpec::with_pids(
            "dx-live-bot",
            "dx-live-bot",
            vec![4242],
        )];
        let recs = recordings_from_execs(&agents, &[exec(9999, "python3")]);
        assert!(!recs[0].detected_anywhere());
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
        let recs = recordings_from_capture(&agents, &[], &connects, &[]);
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
            &[],
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
        let recs =
            recordings_from_capture(&agents, &[], &[connect(9, [8, 8, 8, 8], 53, "curl")], &[]);
        assert!(!recs[0].detected_anywhere());
    }

    #[test]
    fn child_connect_attributed_via_fork_chain() {
        // Spec pids=[100]; pid 100 forked pid 200; a connect from 200 (comm
        // "python3", NOT the marker) is attributed to the agent via the edge.
        let agents = [AgentProcessSpec::with_pids("dx-bot", "dx-bot", vec![100])];
        let recs = recordings_from_capture(
            &agents,
            &[],
            &[connect(200, [127, 0, 0, 1], 9101, "python3")],
            &[fork(100, 200)],
        );
        let visible = recs[0].surfaces.get(&ObservationSurface::EbpfWire).unwrap();
        assert!(visible.contains(&"connect:127.0.0.1:9101".to_string()));
    }

    #[test]
    fn grandchild_attributed_transitively() {
        // 100 -> 200 -> 300; a connect from the grandchild 300 is attributed.
        let agents = [AgentProcessSpec::with_pids("dx-bot", "dx-bot", vec![100])];
        let recs = recordings_from_capture(
            &agents,
            &[],
            &[connect(300, [10, 0, 0, 1], 443, "python3")],
            &[fork(100, 200), fork(200, 300)],
        );
        let visible = recs[0].surfaces.get(&ObservationSurface::EbpfWire).unwrap();
        assert!(visible.contains(&"connect:10.0.0.1:443".to_string()));
    }

    #[test]
    fn unrelated_child_not_attributed() {
        // A fork {999 -> 200} from a pid the agent does not own; a connect from
        // 200 is NOT attributed to a spec with pids=[100].
        let agents = [AgentProcessSpec::with_pids("dx-bot", "dx-bot", vec![100])];
        let recs = recordings_from_capture(
            &agents,
            &[],
            &[connect(200, [8, 8, 8, 8], 53, "python3")],
            &[fork(999, 200)],
        );
        assert!(!recs[0].detected_anywhere());
    }

    #[test]
    fn no_forks_preserves_existing_behavior() {
        // With no fork edges, the prior pid/comm match still works unchanged.
        let agents = [AgentProcessSpec::with_pids("dx-bot", "dx-bot", vec![100])];
        let recs = recordings_from_capture(
            &agents,
            &[exec(100, "python3")],
            &[connect(100, [1, 1, 1, 1], 443, "python3")],
            &[],
        );
        let visible = recs[0].surfaces.get(&ObservationSurface::EbpfWire).unwrap();
        assert!(visible.contains(&"exec:python3:100".to_string()));
        assert!(visible.contains(&"connect:1.1.1.1:443".to_string()));
    }
}
