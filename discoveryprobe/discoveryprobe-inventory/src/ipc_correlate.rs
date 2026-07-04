//! Deriving agent-to-agent communication edges from raw IPC events (Task 10).
//!
//! The kernel probe (Task 9) reconciles a capture window into an [`IpcEvents`]
//! of formatted, sorted, de-duplicated identifiers (the grammar is fixed by
//! `discoveryprobe_core::ipc`):
//!
//! - `listen:<pid>:<port>`            -- a pid serves a local TCP port
//! - `accept:<pid>`                   -- that pid took an inbound connection
//! - `connect:<pid>:<a.b.c.d>:<port>` -- a pid dialed a TCP peer
//! - `unix_connect:<pid>:<path>`      -- a pid dialed an `AF_UNIX` socket
//!
//! This module PARSES those strings back into pid-level facts and correlates
//! them into agent-level [`Edge`]s. It is PURE (I4): zero I/O, zero clock, zero
//! randomness; every intermediate collection is a `BTreeMap`/`BTreeSet`, and
//! the two output lists are sorted and de-duplicated, so the same inputs always
//! yield byte-identical output.
//!
//! Correlation rules (numbered as in the task/design):
//!
//! 1. **Localhost TCP match.** A `connect` whose destination IP is `127.0.0.1`
//!    and whose destination port equals a `listen` port held by ANOTHER pid is
//!    a candidate edge `client_pid -> server_pid`.
//! 2. **`AF_UNIX` accept-pairing (heuristic).** Task 9 emits NO listen event
//!    for an `AF_UNIX` server, only the client's `unix_connect` and a path-less
//!    `accept` on the server side. Because the accept carries no socket path,
//!    the server cannot be matched to a specific `unix_connect` path; the
//!    correlator therefore pairs EACH `unix_connect` (client pid) with EACH
//!    `accept` from a DIFFERENT pid in the same window as a candidate edge
//!    `client_pid -> server_pid`. LIMIT (documented, honest): this
//!    over-approximates -- a path-less `accept` from a TCP server in the same
//!    window would also pair with a Unix client, so a Unix edge may be inferred
//!    where the true server is a TCP one. It never fabricates an AGENT edge for
//!    an unresolvable pid (rule 3), which bounds the noise to co-scheduled,
//!    resolvable agents.
//! 3. **Fork-tree attribution.** Each candidate pid resolves to an agent via
//!    the `pid -> agent_id` map; a pid absent from the map is walked UP the
//!    fork tree (`child_pid -> parent_pid`) until an ancestor pid maps to an
//!    agent. An unresolvable pid DROPS its edge -- never fabricate an agent.
//! 4. **Gateway classification.** A candidate whose resolved DESTINATION agent
//!    is in the caller-provided `gateways` set (R5 config input) is recorded as
//!    a `via_gateway` edge, kept SEPARATE from the direct edges so the
//!    declared-vs-observed diff never flags a broker hop as an undeclared
//!    handoff. LIMIT (documented): the probe's IPC identifiers drop the comm
//!    name, so a gateway is matched by its RESOLVED AGENT ID (via `pid_agents`),
//!    not by a raw process comm string.
//!
//! A candidate whose two endpoints resolve to the SAME agent is dropped (an
//! agent talking to itself is not an inter-agent edge).

use crate::graph::Edge;
use discoveryprobe_core::ipc::IpcEvents;
use std::collections::{BTreeMap, BTreeSet};

/// The IPv4 loopback address the probe emits for a localhost TCP dial.
const LOOPBACK_V4: &str = "127.0.0.1";

/// Agent-level edges derived from raw IPC events, split by gateway status.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct DerivedEdges {
    /// Direct inter-agent edges (destination is not a gateway). Sorted, unique.
    pub direct: Vec<Edge>,
    /// Edges whose destination agent is a gateway (design rule 4). Sorted,
    /// unique; excluded from the undeclared-handoff diff.
    pub via_gateway: Vec<Edge>,
}

/// Correlates raw IPC events into agent-level communication edges (rules 1-4).
///
/// Pure and deterministic (I4): the output is a function of the four inputs,
/// sorted and de-duplicated. `pid_agents` maps a pid to its agent; `forks` are
/// `(parent_pid, child_pid)` edges for fork-tree attribution; `gateways` is the
/// caller-configured set of gateway agent ids. See the module doc for the rules.
pub fn derive_ipc_edges(
    ipc: &IpcEvents,
    forks: &[(u32, u32)],
    pid_agents: &[(u32, String)],
    gateways: &[String],
) -> DerivedEdges {
    let resolver = PidResolver::new(pid_agents, forks);
    let gateway_set: BTreeSet<&str> = gateways.iter().map(String::as_str).collect();

    // Candidate pid-level edges (client_pid -> server_pid), sorted/unique.
    let mut candidates: BTreeSet<(u32, u32)> = BTreeSet::new();

    // Rule 1: localhost TCP connect matching another pid's listen port.
    let mut listeners_by_port: BTreeMap<u16, BTreeSet<u32>> = BTreeMap::new();
    for raw in &ipc.listens {
        if let Some((pid, port)) = parse_listen(raw) {
            listeners_by_port.entry(port).or_default().insert(pid);
        }
    }
    for raw in &ipc.connects {
        if let Some((client_pid, ip, port)) = parse_connect(raw) {
            if ip != LOOPBACK_V4 {
                continue;
            }
            if let Some(servers) = listeners_by_port.get(&port) {
                for &server_pid in servers {
                    if server_pid != client_pid {
                        candidates.insert((client_pid, server_pid));
                    }
                }
            }
        }
    }

    // Rule 2: AF_UNIX accept-pairing heuristic.
    let accept_pids: BTreeSet<u32> = ipc.accepts.iter().filter_map(|s| parse_accept(s)).collect();
    let unix_client_pids: BTreeSet<u32> = ipc
        .unix_connects
        .iter()
        .filter_map(|s| parse_unix_connect(s))
        .collect();
    for &client_pid in &unix_client_pids {
        for &server_pid in &accept_pids {
            if server_pid != client_pid {
                candidates.insert((client_pid, server_pid));
            }
        }
    }

    // Rules 3 + 4: resolve pids to agents (fork-tree), classify by gateway.
    let mut direct: BTreeSet<Edge> = BTreeSet::new();
    let mut via_gateway: BTreeSet<Edge> = BTreeSet::new();
    for (client_pid, server_pid) in candidates {
        let (Some(from), Some(to)) = (resolver.resolve(client_pid), resolver.resolve(server_pid))
        else {
            continue; // unresolvable pid -> drop, never fabricate an agent
        };
        if from == to {
            continue; // same agent talking to itself is not an inter-agent edge
        }
        let edge = Edge {
            from: from.to_string(),
            to: to.to_string(),
        };
        if gateway_set.contains(to) {
            via_gateway.insert(edge);
        } else {
            direct.insert(edge);
        }
    }

    DerivedEdges {
        direct: direct.into_iter().collect(),
        via_gateway: via_gateway.into_iter().collect(),
    }
}

/// Resolves a pid to its agent id, walking the fork tree when the pid is not
/// directly mapped (rule 3). Deterministic: first mapping wins on duplicates.
struct PidResolver<'a> {
    /// Direct `pid -> agent_id` map (first binding wins).
    pid_to_agent: BTreeMap<u32, &'a str>,
    /// `child_pid -> parent_pid` map for the upward fork walk.
    child_to_parent: BTreeMap<u32, u32>,
}

impl<'a> PidResolver<'a> {
    /// Builds the resolver from the pid map and the fork edges.
    fn new(pid_agents: &'a [(u32, String)], forks: &[(u32, u32)]) -> Self {
        let mut pid_to_agent: BTreeMap<u32, &'a str> = BTreeMap::new();
        for (pid, agent) in pid_agents {
            pid_to_agent.entry(*pid).or_insert(agent.as_str());
        }
        let mut child_to_parent: BTreeMap<u32, u32> = BTreeMap::new();
        for (parent, child) in forks {
            child_to_parent.entry(*child).or_insert(*parent);
        }
        Self {
            pid_to_agent,
            child_to_parent,
        }
    }

    /// Resolves `pid` to an agent id: direct hit, else the nearest ancestor pid
    /// in the fork tree that maps to an agent. `None` if none maps (the edge is
    /// then dropped). A `visited` set bounds any cyclic/self fork defensively.
    fn resolve(&self, pid: u32) -> Option<&'a str> {
        let mut cur = pid;
        let mut visited: BTreeSet<u32> = BTreeSet::new();
        loop {
            if let Some(agent) = self.pid_to_agent.get(&cur) {
                return Some(*agent);
            }
            if !visited.insert(cur) {
                return None; // cycle guard (fail-safe)
            }
            match self.child_to_parent.get(&cur) {
                Some(&parent) => cur = parent,
                None => return None,
            }
        }
    }
}

/// Parses `listen:<pid>:<port>` into `(pid, port)`; `None` if malformed.
fn parse_listen(raw: &str) -> Option<(u32, u16)> {
    let rest = raw.strip_prefix("listen:")?;
    let (pid, port) = rest.split_once(':')?;
    Some((pid.parse().ok()?, port.parse().ok()?))
}

/// Parses `accept:<pid>` into `pid`; `None` if malformed.
fn parse_accept(raw: &str) -> Option<u32> {
    raw.strip_prefix("accept:")?.parse().ok()
}

/// Parses `connect:<pid>:<a.b.c.d>:<port>` into `(pid, ip, port)`; `None` if
/// malformed. The IPv4 address holds no ':', so the split is unambiguous.
fn parse_connect(raw: &str) -> Option<(u32, String, u16)> {
    let rest = raw.strip_prefix("connect:")?;
    let (pid, after_pid) = rest.split_once(':')?;
    let (ip, port) = after_pid.rsplit_once(':')?;
    Some((pid.parse().ok()?, ip.to_string(), port.parse().ok()?))
}

/// Parses `unix_connect:<pid>:<path>` into the client `pid`; `None` if
/// malformed. The path (which may be empty for an abstract socket, or contain
/// ':') is not needed for the accept-pairing heuristic, so only the pid is kept.
fn parse_unix_connect(raw: &str) -> Option<u32> {
    let rest = raw.strip_prefix("unix_connect:")?;
    let (pid, _path) = rest.split_once(':')?;
    pid.parse().ok()
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Shorthand edge constructor for assertions.
    fn edge(from: &str, to: &str) -> Edge {
        Edge {
            from: from.to_string(),
            to: to.to_string(),
        }
    }

    /// Shorthand `(pid, agent)` mapping constructor.
    fn map(pid: u32, agent: &str) -> (u32, String) {
        (pid, agent.to_string())
    }

    #[test]
    fn localhost_connect_matching_a_listen_becomes_an_observed_edge() {
        // pid10 = agent-a connects 127.0.0.1:9000; pid20 = agent-b listens :9000.
        let ipc = IpcEvents {
            listens: vec!["listen:20:9000".to_string()],
            accepts: vec![],
            connects: vec!["connect:10:127.0.0.1:9000".to_string()],
            unix_connects: vec![],
        };
        let pid_agents = vec![map(10, "agent-a"), map(20, "agent-b")];
        let derived = derive_ipc_edges(&ipc, &[], &pid_agents, &[]);
        assert_eq!(derived.direct, vec![edge("agent-a", "agent-b")]);
        assert!(derived.via_gateway.is_empty());
    }

    #[test]
    fn unix_socket_path_match_becomes_an_observed_edge() {
        // pid10 = agent-a dials a Unix socket; pid20 = agent-b accepts (path-less).
        let ipc = IpcEvents {
            listens: vec![],
            accepts: vec!["accept:20".to_string()],
            connects: vec![],
            unix_connects: vec!["unix_connect:10:/run/mesh.sock".to_string()],
        };
        let pid_agents = vec![map(10, "agent-a"), map(20, "agent-b")];
        let derived = derive_ipc_edges(&ipc, &[], &pid_agents, &[]);
        assert_eq!(derived.direct, vec![edge("agent-a", "agent-b")]);
    }

    #[test]
    fn fork_tree_attributes_child_pid_activity_to_the_parent_agent() {
        // pid30 (a fork child of pid10 = agent-a) connects; pid20 = agent-b
        // listens. pid30 is NOT directly mapped: it resolves via the fork tree.
        let ipc = IpcEvents {
            listens: vec!["listen:20:9000".to_string()],
            accepts: vec![],
            connects: vec!["connect:30:127.0.0.1:9000".to_string()],
            unix_connects: vec![],
        };
        let pid_agents = vec![map(10, "agent-a"), map(20, "agent-b")];
        let forks = vec![(10u32, 30u32)]; // agent-a's pid forked pid30
        let derived = derive_ipc_edges(&ipc, &forks, &pid_agents, &[]);
        assert_eq!(derived.direct, vec![edge("agent-a", "agent-b")]);
    }

    #[test]
    fn edge_to_a_known_gateway_process_is_marked_via_gateway_not_inferred() {
        // Destination pid20 resolves to the gateway agent "broker": the edge is
        // via_gateway, NOT a direct inter-agent edge.
        let ipc = IpcEvents {
            listens: vec!["listen:20:9000".to_string()],
            accepts: vec![],
            connects: vec!["connect:10:127.0.0.1:9000".to_string()],
            unix_connects: vec![],
        };
        let pid_agents = vec![map(10, "agent-a"), map(20, "broker")];
        let gateways = vec!["broker".to_string()];
        let derived = derive_ipc_edges(&ipc, &[], &pid_agents, &gateways);
        assert!(derived.direct.is_empty());
        assert_eq!(derived.via_gateway, vec![edge("agent-a", "broker")]);
    }

    #[test]
    fn localhost_connect_with_no_matching_listen_is_not_an_edge() {
        // Connect to :9999, but the only listen is on :9000 -> no edge (negative).
        let ipc = IpcEvents {
            listens: vec!["listen:20:9000".to_string()],
            accepts: vec![],
            connects: vec!["connect:10:127.0.0.1:9999".to_string()],
            unix_connects: vec![],
        };
        let pid_agents = vec![map(10, "agent-a"), map(20, "agent-b")];
        let derived = derive_ipc_edges(&ipc, &[], &pid_agents, &[]);
        assert!(derived.direct.is_empty());
        assert!(derived.via_gateway.is_empty());
    }

    #[test]
    fn non_localhost_connect_matching_a_port_is_not_a_local_edge() {
        // A connect to a NON-loopback peer on the same port is external egress,
        // never a localhost inter-agent edge (rule 1 requires 127.0.0.1).
        let ipc = IpcEvents {
            listens: vec!["listen:20:9000".to_string()],
            accepts: vec![],
            connects: vec!["connect:10:10.0.0.5:9000".to_string()],
            unix_connects: vec![],
        };
        let pid_agents = vec![map(10, "agent-a"), map(20, "agent-b")];
        let derived = derive_ipc_edges(&ipc, &[], &pid_agents, &[]);
        assert!(derived.direct.is_empty());
    }

    #[test]
    fn unresolvable_pid_drops_the_edge_never_fabricates_an_agent() {
        // The server pid20 maps to no agent and has no fork ancestor: the edge
        // is dropped, not attributed to an invented agent.
        let ipc = IpcEvents {
            listens: vec!["listen:20:9000".to_string()],
            accepts: vec![],
            connects: vec!["connect:10:127.0.0.1:9000".to_string()],
            unix_connects: vec![],
        };
        let pid_agents = vec![map(10, "agent-a")]; // 20 unmapped
        let derived = derive_ipc_edges(&ipc, &[], &pid_agents, &[]);
        assert!(derived.direct.is_empty());
        assert!(derived.via_gateway.is_empty());
    }

    #[test]
    fn same_agent_endpoints_are_not_an_inter_agent_edge() {
        // Client and server pids both resolve to agent-a: no self inter-agent edge.
        let ipc = IpcEvents {
            listens: vec!["listen:11:9000".to_string()],
            accepts: vec![],
            connects: vec!["connect:10:127.0.0.1:9000".to_string()],
            unix_connects: vec![],
        };
        let pid_agents = vec![map(10, "agent-a"), map(11, "agent-a")];
        let derived = derive_ipc_edges(&ipc, &[], &pid_agents, &[]);
        assert!(derived.direct.is_empty());
    }

    #[test]
    fn derivation_is_deterministic_and_sorted() {
        // Two edges out of order across surfaces must normalise identically.
        let ipc = IpcEvents {
            listens: vec!["listen:20:9000".to_string(), "listen:40:9001".to_string()],
            accepts: vec![],
            connects: vec![
                "connect:30:127.0.0.1:9001".to_string(),
                "connect:10:127.0.0.1:9000".to_string(),
            ],
            unix_connects: vec![],
        };
        let pid_agents = vec![
            map(10, "agent-a"),
            map(20, "agent-b"),
            map(30, "agent-c"),
            map(40, "agent-d"),
        ];
        let run_a = derive_ipc_edges(&ipc, &[], &pid_agents, &[]);
        let run_b = derive_ipc_edges(&ipc, &[], &pid_agents, &[]);
        assert_eq!(run_a, run_b);
        assert_eq!(
            run_a.direct,
            vec![edge("agent-a", "agent-b"), edge("agent-c", "agent-d")]
        );
    }
}
