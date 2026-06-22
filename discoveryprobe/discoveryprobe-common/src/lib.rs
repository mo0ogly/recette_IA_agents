//! Capture event layout shared by the discoveryprobe eBPF kernel program and the
//! userspace loader.
//!
//! The kernel program writes one [`ExecEvent`] per observed process exec into a
//! ring buffer; the userspace loader reads the raw bytes back and parses them
//! with [`ExecEvent::from_bytes`]. The struct is `#[repr(C)]` so its layout is
//! identical on both sides, and this crate carries ZERO dependencies so it
//! compiles unchanged for the host (std tests) and the `bpfel-unknown-none`
//! target (build-std core only).

#![cfg_attr(not(test), no_std)]

/// Length of the kernel `comm` field (`TASK_COMM_LEN`, the process name).
pub const COMM_LEN: usize = 16;

/// One captured process-exec event: which process (`pid`) ran, under what
/// command name (`comm`). This is the kernel's evidence that an agent process
/// exists -- the eBPF view of "the agent is running", visible even when the
/// process lives inside a Docker container (one shared kernel).
#[repr(C)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ExecEvent {
    /// The process id (thread-group leader) that called exec.
    pub pid: u32,
    /// The process command name, NUL-padded (`bpf_get_current_comm`).
    pub comm: [u8; COMM_LEN],
}

/// Wire size of a serialised [`ExecEvent`] -- the exact byte count the kernel
/// reserves in the ring buffer and the loader reads back.
pub const EXEC_EVENT_SIZE: usize = core::mem::size_of::<ExecEvent>();

impl ExecEvent {
    /// Parse one event from raw ring-buffer bytes (native endianness: the
    /// kernel producer and the userspace consumer share one host). Returns
    /// `None` if the slice is too short.
    pub fn from_bytes(buf: &[u8]) -> Option<Self> {
        if buf.len() < EXEC_EVENT_SIZE {
            return None;
        }
        let pid = u32::from_ne_bytes([buf[0], buf[1], buf[2], buf[3]]);
        let mut comm = [0u8; COMM_LEN];
        comm.copy_from_slice(&buf[4..4 + COMM_LEN]);
        Some(Self { pid, comm })
    }

    /// The command name as a string slice, trimmed at the first NUL. Returns an
    /// empty slice if the bytes are not valid UTF-8.
    pub fn comm_str(&self) -> &str {
        let end = self.comm.iter().position(|&b| b == 0).unwrap_or(COMM_LEN);
        core::str::from_utf8(&self.comm[..end]).unwrap_or("")
    }
}

/// One captured outbound TCP `connect`: which process (`pid`/`comm`) opened a
/// connection to which IPv4 destination (`daddr:dport`).
///
/// This is the kernel's evidence of an agent's network egress -- for an LLM
/// agent, the HTTPS connection to the provider (e.g. `api.openai.com:443`).
/// cyberark/agentwatch observes this at the `httpcore`/HTTP transport layer
/// in-process; capturing the `connect` syscall sees the same egress at the
/// kernel, WITHOUT the agent's cooperation -- the eBPF-wire surface, so a
/// hook-blind ("ghost") agent is still caught on the wire.
///
/// The address fields are stored as their on-wire network-byte-order bytes
/// (`sin_addr` / `sin_port`), so parsing is endianness-unambiguous: the octets
/// are formatted in order and the port is read big-endian. IPv4 only for now
/// (the simulated agents connect over IPv4); an IPv6 variant is a later step.
#[repr(C)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ConnectEvent {
    /// The process id (thread-group leader) that called `connect`.
    pub pid: u32,
    /// Destination IPv4 address octets, in network order (`sin_addr.s_addr`).
    pub daddr: [u8; 4],
    /// Destination port bytes, in network order / big-endian (`sin_port`).
    pub dport: [u8; 2],
    /// Explicit padding so `repr(C)` size is fixed and deterministic on both
    /// the kernel producer and userspace consumer.
    pub _pad: [u8; 2],
    /// The process command name, NUL-padded (`bpf_get_current_comm`).
    pub comm: [u8; COMM_LEN],
}

/// Wire size of a serialised [`ConnectEvent`] -- the exact byte count the kernel
/// reserves in the ring buffer and the loader reads back.
pub const CONNECT_EVENT_SIZE: usize = core::mem::size_of::<ConnectEvent>();

impl ConnectEvent {
    /// Parse one event from raw ring-buffer bytes. The `pid` is host-native
    /// (the kernel producer and userspace consumer share one host); the address
    /// and port bytes are kept in network order. Returns `None` if too short.
    pub fn from_bytes(buf: &[u8]) -> Option<Self> {
        if buf.len() < CONNECT_EVENT_SIZE {
            return None;
        }
        let pid = u32::from_ne_bytes([buf[0], buf[1], buf[2], buf[3]]);
        let daddr = [buf[4], buf[5], buf[6], buf[7]];
        let dport = [buf[8], buf[9]];
        let _pad = [buf[10], buf[11]];
        let mut comm = [0u8; COMM_LEN];
        comm.copy_from_slice(&buf[12..12 + COMM_LEN]);
        Some(Self {
            pid,
            daddr,
            dport,
            _pad,
            comm,
        })
    }

    /// The destination port in host order (the network-order bytes read
    /// big-endian).
    pub fn port(&self) -> u16 {
        u16::from_be_bytes(self.dport)
    }

    /// The four destination IPv4 octets, in order. Userspace formats these as
    /// `a.b.c.d` (this crate stays alloc-free for the `core`-only eBPF build).
    pub fn octets(&self) -> [u8; 4] {
        self.daddr
    }

    /// The command name as a string slice, trimmed at the first NUL. Returns an
    /// empty slice if the bytes are not valid UTF-8.
    pub fn comm_str(&self) -> &str {
        let end = self.comm.iter().position(|&b| b == 0).unwrap_or(COMM_LEN);
        core::str::from_utf8(&self.comm[..end]).unwrap_or("")
    }
}

/// One captured process fork: a `parent_pid` spawned a `child_pid`
/// (`sched:sched_process_fork`). Lets the userspace mapping attribute a child
/// process's activity (exec/connect) to the agent that owns the parent pid --
/// the process-tree view, so a multi-process agent is not a blind spot.
#[repr(C)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ForkEvent {
    /// The parent process id (thread-group leader) that forked.
    pub parent_pid: u32,
    /// The child process id created by the fork.
    pub child_pid: u32,
}

/// Wire size of a serialised [`ForkEvent`] -- the exact byte count the kernel
/// reserves in the ring buffer and the loader reads back.
pub const FORK_EVENT_SIZE: usize = core::mem::size_of::<ForkEvent>();

impl ForkEvent {
    /// Parse one event from raw ring-buffer bytes (native endianness: the
    /// kernel producer and the userspace consumer share one host). Returns
    /// `None` if the slice is too short.
    pub fn from_bytes(buf: &[u8]) -> Option<Self> {
        if buf.len() < FORK_EVENT_SIZE {
            return None;
        }
        let parent_pid = u32::from_ne_bytes([buf[0], buf[1], buf[2], buf[3]]);
        let child_pid = u32::from_ne_bytes([buf[4], buf[5], buf[6], buf[7]]);
        Some(Self {
            parent_pid,
            child_pid,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make(pid: u32, name: &str) -> ExecEvent {
        let mut comm = [0u8; COMM_LEN];
        let bytes = name.as_bytes();
        let n = bytes.len().min(COMM_LEN);
        comm[..n].copy_from_slice(&bytes[..n]);
        ExecEvent { pid, comm }
    }

    fn to_bytes(ev: &ExecEvent) -> Vec<u8> {
        let mut buf = Vec::with_capacity(EXEC_EVENT_SIZE);
        buf.extend_from_slice(&ev.pid.to_ne_bytes());
        buf.extend_from_slice(&ev.comm);
        buf
    }

    #[test]
    fn exec_event_size_is_pid_plus_comm() {
        assert_eq!(EXEC_EVENT_SIZE, 4 + COMM_LEN);
    }

    #[test]
    fn from_bytes_round_trips_pid_and_comm() {
        let ev = make(4242, "pr-bot");
        let parsed = ExecEvent::from_bytes(&to_bytes(&ev)).expect("parse");
        assert_eq!(parsed, ev);
    }

    #[test]
    fn comm_str_trims_at_nul() {
        let ev = make(1, "agent");
        assert_eq!(ev.comm_str(), "agent");
    }

    #[test]
    fn from_bytes_rejects_short_slice() {
        assert!(ExecEvent::from_bytes(&[0u8; EXEC_EVENT_SIZE - 1]).is_none());
    }

    fn make_connect(pid: u32, daddr: [u8; 4], port: u16, name: &str) -> ConnectEvent {
        let mut comm = [0u8; COMM_LEN];
        let bytes = name.as_bytes();
        let n = bytes.len().min(COMM_LEN);
        comm[..n].copy_from_slice(&bytes[..n]);
        ConnectEvent {
            pid,
            daddr,
            dport: port.to_be_bytes(),
            _pad: [0u8; 2],
            comm,
        }
    }

    fn connect_to_bytes(ev: &ConnectEvent) -> Vec<u8> {
        let mut buf = Vec::with_capacity(CONNECT_EVENT_SIZE);
        buf.extend_from_slice(&ev.pid.to_ne_bytes());
        buf.extend_from_slice(&ev.daddr);
        buf.extend_from_slice(&ev.dport);
        buf.extend_from_slice(&ev._pad);
        buf.extend_from_slice(&ev.comm);
        buf
    }

    #[test]
    fn connect_event_size_is_pid_addr_port_pad_comm() {
        assert_eq!(CONNECT_EVENT_SIZE, 4 + 4 + 2 + 2 + COMM_LEN);
    }

    #[test]
    fn connect_from_bytes_round_trips() {
        let ev = make_connect(99, [140, 82, 112, 3], 443, "pr-bot");
        let parsed = ConnectEvent::from_bytes(&connect_to_bytes(&ev)).expect("parse");
        assert_eq!(parsed, ev);
    }

    #[test]
    fn connect_port_reads_network_order_big_endian() {
        let ev = make_connect(1, [1, 2, 3, 4], 443, "a");
        assert_eq!(ev.port(), 443);
        assert_eq!(ev.octets(), [1, 2, 3, 4]);
    }

    #[test]
    fn connect_from_bytes_rejects_short_slice() {
        assert!(ConnectEvent::from_bytes(&[0u8; CONNECT_EVENT_SIZE - 1]).is_none());
    }

    fn fork_to_bytes(ev: &ForkEvent) -> Vec<u8> {
        let mut buf = Vec::with_capacity(FORK_EVENT_SIZE);
        buf.extend_from_slice(&ev.parent_pid.to_ne_bytes());
        buf.extend_from_slice(&ev.child_pid.to_ne_bytes());
        buf
    }

    #[test]
    fn fork_event_size_is_two_pids() {
        assert_eq!(FORK_EVENT_SIZE, 4 + 4);
    }

    #[test]
    fn fork_from_bytes_round_trips_parent_and_child() {
        let ev = ForkEvent {
            parent_pid: 100,
            child_pid: 200,
        };
        let parsed = ForkEvent::from_bytes(&fork_to_bytes(&ev)).expect("parse");
        assert_eq!(parsed, ev);
    }

    #[test]
    fn fork_from_bytes_rejects_short_slice() {
        assert!(ForkEvent::from_bytes(&[0u8; FORK_EVENT_SIZE - 1]).is_none());
    }
}
