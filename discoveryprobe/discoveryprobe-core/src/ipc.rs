//! Inter-agent communication surface reconciled from the kernel probe.
//!
//! Task 9 extends the eBPF probe to capture the localhost/IPC edges an agent
//! mesh uses to talk to itself: a TCP server ([`ListenEvent`] + [`AcceptEvent`]),
//! a TCP client ([`ConnectEvent`], reused), and an `AF_UNIX` client
//! ([`UnixConnectEvent`]). This module turns those raw captures into a single
//! serde [`IpcEvents`] the Python surface judge and the console consume -- the
//! bridge contract for "which agent talks to which".
//!
//! Determinism (I4): every field is a SORTED, de-duplicated `Vec<String>` (built
//! through a [`BTreeSet`]), so the same captures serialise byte-for-byte
//! identically regardless of the non-deterministic capture order. The live
//! capture is non-deterministic by nature; freezing it through this pure
//! function is what makes the downstream judgement replay-stable.

use std::collections::BTreeSet;

use serde::{Deserialize, Serialize};

use discoveryprobe_common::{AcceptEvent, ConnectEvent, ListenEvent, UnixConnectEvent};

/// The inter-agent communication surface: the reconciled listen/accept/connect/
/// unix-connect view of one capture window. Each field is a sorted, deduplicated
/// list of stable string identifiers (I4).
///
/// Identifier grammar (stable -- the Python side parses these):
/// - listen:       `listen:<pid>:<port>`            (a pid serves a local TCP port)
/// - accept:       `accept:<pid>`                   (that pid took an inbound conn)
/// - connect:      `connect:<pid>:<a.b.c.d>:<port>` (a pid dialed a TCP peer)
/// - unix_connect: `unix_connect:<pid>:<path>`      (a pid dialed a Unix socket)
///
/// A listen/accept on a pid paired with another pid's `connect` to the same
/// `127.0.0.1:port` is an observed agent-to-agent edge; a `unix_connect` path
/// matched against a bound Unix socket is the same edge over a socket file. The
/// pairing itself is done downstream; this type is the normalised evidence.
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct IpcEvents {
    /// TCP listen endpoints: `listen:<pid>:<port>`.
    pub listens: Vec<String>,
    /// TCP accepts (a live server actually took a connection): `accept:<pid>`.
    pub accepts: Vec<String>,
    /// Outbound TCP connects (reused from the egress capture, the client side of
    /// a localhost edge): `connect:<pid>:<a.b.c.d>:<port>`.
    pub connects: Vec<String>,
    /// `AF_UNIX` connects (local IPC dial over a socket file): `unix_connect:<pid>:<path>`.
    pub unix_connects: Vec<String>,
}

/// Format a listen event as its stable identifier.
fn fmt_listen(ev: &ListenEvent) -> String {
    format!("listen:{}:{}", ev.pid, ev.port())
}

/// Format an accept event as its stable identifier.
fn fmt_accept(ev: &AcceptEvent) -> String {
    format!("accept:{}", ev.pid)
}

/// Format a connect event as its stable identifier (pid + dotted IPv4 + port).
fn fmt_connect(ev: &ConnectEvent) -> String {
    let o = ev.octets();
    format!(
        "connect:{}:{}.{}.{}.{}:{}",
        ev.pid,
        o[0],
        o[1],
        o[2],
        o[3],
        ev.port()
    )
}

/// Format an `AF_UNIX` connect event as its stable identifier (pid + path). An
/// abstract-namespace socket reports an empty path (see [`UnixConnectEvent`]).
fn fmt_unix_connect(ev: &UnixConnectEvent) -> String {
    format!("unix_connect:{}:{}", ev.pid, ev.path_str())
}

/// Collect a slice of events into a sorted, de-duplicated `Vec<String>` via the
/// given formatter -- the single normalisation primitive that makes every field
/// replay-stable (I4).
fn sorted<T>(events: &[T], fmt: impl Fn(&T) -> String) -> Vec<String> {
    events
        .iter()
        .map(fmt)
        .collect::<BTreeSet<String>>()
        .into_iter()
        .collect()
}

impl IpcEvents {
    /// Build the reconciled IPC surface from the four raw capture slices.
    ///
    /// Pure and deterministic: each field is sorted and de-duplicated, so the
    /// same captures produce a byte-identical [`IpcEvents`] (I4).
    pub fn from_events(
        listens: &[ListenEvent],
        accepts: &[AcceptEvent],
        connects: &[ConnectEvent],
        unix_connects: &[UnixConnectEvent],
    ) -> Self {
        Self {
            listens: sorted(listens, fmt_listen),
            accepts: sorted(accepts, fmt_accept),
            connects: sorted(connects, fmt_connect),
            unix_connects: sorted(unix_connects, fmt_unix_connect),
        }
    }

    /// True iff no inter-agent comm was observed on any of the four surfaces.
    pub fn is_empty(&self) -> bool {
        self.listens.is_empty()
            && self.accepts.is_empty()
            && self.connects.is_empty()
            && self.unix_connects.is_empty()
    }

    /// Serialise to the bridge JSON. Already normalised at construction, so the
    /// output is deterministic regardless of the capture order.
    pub fn to_json(&self) -> Result<String, serde_json::Error> {
        serde_json::to_string(self)
    }

    /// Parse an [`IpcEvents`] back from the bridge JSON.
    pub fn from_json(raw: &str) -> Result<Self, serde_json::Error> {
        serde_json::from_str(raw)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use discoveryprobe_common::{
        AcceptEvent, ConnectEvent, ListenEvent, UnixConnectEvent, ACCEPT_EVENT_SIZE, COMM_LEN,
        CONNECT_EVENT_SIZE, LISTEN_EVENT_SIZE, UNIX_CONNECT_EVENT_SIZE, UNIX_PATH_LEN,
    };

    // --- raw-byte fixture builders: assemble the exact ring-buffer wire bytes,
    // then parse them back with the `*_from_bytes` decoders (the same path the
    // loader uses), so the formatting is tested against the real wire layout.

    fn comm_bytes(name: &str) -> [u8; COMM_LEN] {
        let mut comm = [0u8; COMM_LEN];
        let b = name.as_bytes();
        let n = b.len().min(COMM_LEN);
        comm[..n].copy_from_slice(&b[..n]);
        comm
    }

    fn listen_bytes(pid: u32, port: u16, name: &str) -> Vec<u8> {
        let mut buf = Vec::with_capacity(LISTEN_EVENT_SIZE);
        buf.extend_from_slice(&pid.to_ne_bytes());
        buf.extend_from_slice(&port.to_be_bytes()); // network order (as the kernel holds it)
        buf.extend_from_slice(&[0u8, 0u8]); // _pad
        buf.extend_from_slice(&comm_bytes(name));
        buf
    }

    fn accept_bytes(pid: u32, name: &str) -> Vec<u8> {
        let mut buf = Vec::with_capacity(ACCEPT_EVENT_SIZE);
        buf.extend_from_slice(&pid.to_ne_bytes());
        buf.extend_from_slice(&comm_bytes(name));
        buf
    }

    fn connect_bytes(pid: u32, daddr: [u8; 4], port: u16, name: &str) -> Vec<u8> {
        let mut buf = Vec::with_capacity(CONNECT_EVENT_SIZE);
        buf.extend_from_slice(&pid.to_ne_bytes());
        buf.extend_from_slice(&daddr);
        buf.extend_from_slice(&port.to_be_bytes());
        buf.extend_from_slice(&[0u8, 0u8]); // _pad
        buf.extend_from_slice(&comm_bytes(name));
        buf
    }

    fn unix_connect_bytes(pid: u32, path: &str, name: &str) -> Vec<u8> {
        let mut buf = Vec::with_capacity(UNIX_CONNECT_EVENT_SIZE);
        buf.extend_from_slice(&pid.to_ne_bytes());
        buf.extend_from_slice(&comm_bytes(name));
        let mut path_buf = [0u8; UNIX_PATH_LEN];
        let pb = path.as_bytes();
        let pn = pb.len().min(UNIX_PATH_LEN);
        path_buf[..pn].copy_from_slice(&pb[..pn]);
        buf.extend_from_slice(&path_buf);
        buf
    }

    fn listen(pid: u32, port: u16, name: &str) -> ListenEvent {
        ListenEvent::from_bytes(&listen_bytes(pid, port, name)).expect("parse listen")
    }
    fn accept(pid: u32, name: &str) -> AcceptEvent {
        AcceptEvent::from_bytes(&accept_bytes(pid, name)).expect("parse accept")
    }
    fn connect(pid: u32, daddr: [u8; 4], port: u16, name: &str) -> ConnectEvent {
        ConnectEvent::from_bytes(&connect_bytes(pid, daddr, port, name)).expect("parse connect")
    }
    fn unix_connect(pid: u32, path: &str, name: &str) -> UnixConnectEvent {
        UnixConnectEvent::from_bytes(&unix_connect_bytes(pid, path, name)).expect("parse unix")
    }

    #[test]
    fn listen_formats_pid_and_host_port() {
        // Port bytes on the wire are network order; port() reads them big-endian.
        let ev = listen(4242, 8082, "mcp-server");
        let ipc = IpcEvents::from_events(&[ev], &[], &[], &[]);
        assert_eq!(ipc.listens, vec!["listen:4242:8082".to_string()]);
    }

    #[test]
    fn accept_formats_pid_only() {
        let ev = accept(4242, "mcp-server");
        let ipc = IpcEvents::from_events(&[], &[ev], &[], &[]);
        assert_eq!(ipc.accepts, vec!["accept:4242".to_string()]);
    }

    #[test]
    fn connect_formats_pid_dotted_ipv4_and_port() {
        let ev = connect(99, [127, 0, 0, 1], 9101, "worker");
        let ipc = IpcEvents::from_events(&[], &[], &[ev], &[]);
        assert_eq!(ipc.connects, vec!["connect:99:127.0.0.1:9101".to_string()]);
    }

    #[test]
    fn unix_connect_formats_pid_and_path() {
        let ev = unix_connect(7, "/run/agent/grpc.sock", "worker");
        let ipc = IpcEvents::from_events(&[], &[], &[], &[ev]);
        assert_eq!(
            ipc.unix_connects,
            vec!["unix_connect:7:/run/agent/grpc.sock".to_string()]
        );
    }

    #[test]
    fn unix_connect_abstract_socket_reports_empty_path() {
        // A leading-NUL (abstract-namespace) path is trimmed to empty by
        // path_str; the connect is still recorded with its pid.
        let mut bytes = unix_connect_bytes(7, "", "worker");
        // path starts at 4 + COMM_LEN; leading NUL then a name byte (abstract).
        let path_start = 4 + COMM_LEN;
        bytes[path_start] = 0;
        bytes[path_start + 1] = b'x';
        let ev = UnixConnectEvent::from_bytes(&bytes).expect("parse");
        let ipc = IpcEvents::from_events(&[], &[], &[], &[ev]);
        assert_eq!(ipc.unix_connects, vec!["unix_connect:7:".to_string()]);
    }

    #[test]
    fn every_field_is_sorted_and_deduplicated() {
        // Out-of-order + duplicate inputs across every field must normalise to a
        // sorted, deduplicated list (I4).
        let listens = [listen(9, 80, "s"), listen(2, 80, "s"), listen(9, 80, "s")];
        let accepts = [accept(9, "s"), accept(2, "s"), accept(9, "s")];
        let connects = [
            connect(9, [10, 0, 0, 2], 443, "c"),
            connect(2, [10, 0, 0, 1], 443, "c"),
            connect(9, [10, 0, 0, 2], 443, "c"),
        ];
        let unix = [
            unix_connect(9, "/b.sock", "c"),
            unix_connect(2, "/a.sock", "c"),
            unix_connect(9, "/b.sock", "c"),
        ];
        let ipc = IpcEvents::from_events(&listens, &accepts, &connects, &unix);
        assert_eq!(
            ipc.listens,
            vec!["listen:2:80".to_string(), "listen:9:80".to_string()]
        );
        assert_eq!(
            ipc.accepts,
            vec!["accept:2".to_string(), "accept:9".to_string()]
        );
        assert_eq!(
            ipc.connects,
            vec![
                "connect:2:10.0.0.1:443".to_string(),
                "connect:9:10.0.0.2:443".to_string()
            ]
        );
        assert_eq!(
            ipc.unix_connects,
            vec![
                "unix_connect:2:/a.sock".to_string(),
                "unix_connect:9:/b.sock".to_string()
            ]
        );
    }

    #[test]
    fn json_round_trips_and_is_byte_stable() {
        let a = IpcEvents::from_events(
            &[listen(2, 8090, "s"), listen(1, 8082, "s")],
            &[accept(1, "s")],
            &[connect(3, [1, 2, 3, 4], 443, "c")],
            &[unix_connect(4, "/tmp/mcp.sock", "c")],
        );
        // Same inputs in a different order produce byte-identical JSON.
        let b = IpcEvents::from_events(
            &[listen(1, 8082, "s"), listen(2, 8090, "s")],
            &[accept(1, "s")],
            &[connect(3, [1, 2, 3, 4], 443, "c")],
            &[unix_connect(4, "/tmp/mcp.sock", "c")],
        );
        let ja = a.to_json().expect("json a");
        let jb = b.to_json().expect("json b");
        assert_eq!(ja, jb);
        let parsed = IpcEvents::from_json(&ja).expect("round-trip");
        assert_eq!(parsed, a);
    }

    #[test]
    fn empty_capture_is_empty() {
        let ipc = IpcEvents::from_events(&[], &[], &[], &[]);
        assert!(ipc.is_empty());
    }
}
