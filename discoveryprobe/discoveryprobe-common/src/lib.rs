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

/// Length cap for a captured open path (bounded for the eBPF stack/ring).
pub const PATH_LEN: usize = 128;

/// Length cap for a captured DNS query name (bounded for the eBPF stack/ring).
/// A power of two so the kernel-side parse can mask its write index with
/// `& (QNAME_LEN - 1)` to satisfy the verifier (a constant-bounded buffer).
pub const QNAME_LEN: usize = 256;

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

/// One captured file open (`syscalls:sys_enter_openat`): which process
/// (`pid`/`comm`) opened which `path` (NUL-padded, truncated to PATH_LEN). The
/// data-access surface -- what files an agent touches, visible at the kernel
/// without the agent's cooperation.
#[repr(C)]
#[derive(Debug, Clone, Copy)]
pub struct FileEvent {
    /// The process id (thread-group leader) that called `openat`.
    pub pid: u32,
    /// The process command name, NUL-padded (`bpf_get_current_comm`).
    pub comm: [u8; COMM_LEN],
    /// The opened path, NUL-padded, truncated to [`PATH_LEN`]
    /// (`bpf_probe_read_user_str_bytes` of the userspace `filename` argument).
    pub path: [u8; PATH_LEN],
}

/// Wire size of a serialised [`FileEvent`] -- the exact byte count the kernel
/// reserves in the ring buffer and the loader reads back.
pub const FILE_EVENT_SIZE: usize = core::mem::size_of::<FileEvent>();

impl FileEvent {
    /// Parse one event from raw ring-buffer bytes (native endianness: the
    /// kernel producer and the userspace consumer share one host). Returns
    /// `None` if the slice is too short.
    pub fn from_bytes(buf: &[u8]) -> Option<Self> {
        if buf.len() < FILE_EVENT_SIZE {
            return None;
        }
        let pid = u32::from_ne_bytes([buf[0], buf[1], buf[2], buf[3]]);
        let mut comm = [0u8; COMM_LEN];
        comm.copy_from_slice(&buf[4..4 + COMM_LEN]);
        let mut path = [0u8; PATH_LEN];
        let path_start = 4 + COMM_LEN;
        path.copy_from_slice(&buf[path_start..path_start + PATH_LEN]);
        Some(Self { pid, comm, path })
    }

    /// The command name as a string slice, trimmed at the first NUL. Returns an
    /// empty slice if the bytes are not valid UTF-8.
    pub fn comm_str(&self) -> &str {
        let end = self.comm.iter().position(|&b| b == 0).unwrap_or(COMM_LEN);
        core::str::from_utf8(&self.comm[..end]).unwrap_or("")
    }

    /// The opened path as a string slice, trimmed at the first NUL. Returns an
    /// empty slice if the bytes are not valid UTF-8.
    pub fn path_str(&self) -> &str {
        let end = self.path.iter().position(|&b| b == 0).unwrap_or(PATH_LEN);
        core::str::from_utf8(&self.path[..end]).unwrap_or("")
    }
}

/// One captured DNS query (`syscalls:sys_enter_sendto` filtered to a UDP packet
/// whose destination is `AF_INET:53`): which process (`pid`/`comm`) resolved
/// which name (`qname`, the dotted query name parsed from the DNS message's
/// QNAME, NUL-padded, truncated to [`QNAME_LEN`]).
///
/// This is the kernel's evidence of an agent's name resolution -- for an LLM
/// agent, the lookup of its provider host (e.g. `api.openai.com`) BEFORE the
/// HTTPS dial captured by [`ConnectEvent`]. Seen at the kernel without the
/// agent's cooperation (the eBPF-wire surface), so a hook-blind ghost is still
/// caught resolving names.
#[repr(C)]
#[derive(Debug, Clone, Copy)]
pub struct DnsEvent {
    /// The process id (thread-group leader) that called `sendto`.
    pub pid: u32,
    /// The process command name, NUL-padded (`bpf_get_current_comm`).
    pub comm: [u8; COMM_LEN],
    /// The dotted DNS query name, NUL-padded, truncated to [`QNAME_LEN`]
    /// (parsed from the DNS message QNAME labels in the `sendto` payload).
    pub qname: [u8; QNAME_LEN],
}

/// Wire size of a serialised [`DnsEvent`] -- the exact byte count the kernel
/// reserves in the ring buffer and the loader reads back.
pub const DNS_EVENT_SIZE: usize = core::mem::size_of::<DnsEvent>();

impl DnsEvent {
    /// Parse one event from raw ring-buffer bytes (native endianness: the
    /// kernel producer and the userspace consumer share one host). Returns
    /// `None` if the slice is too short.
    pub fn from_bytes(buf: &[u8]) -> Option<Self> {
        if buf.len() < DNS_EVENT_SIZE {
            return None;
        }
        let pid = u32::from_ne_bytes([buf[0], buf[1], buf[2], buf[3]]);
        let mut comm = [0u8; COMM_LEN];
        comm.copy_from_slice(&buf[4..4 + COMM_LEN]);
        let mut qname = [0u8; QNAME_LEN];
        let qname_start = 4 + COMM_LEN;
        qname.copy_from_slice(&buf[qname_start..qname_start + QNAME_LEN]);
        Some(Self { pid, comm, qname })
    }

    /// The command name as a string slice, trimmed at the first NUL. Returns an
    /// empty slice if the bytes are not valid UTF-8.
    pub fn comm_str(&self) -> &str {
        let end = self.comm.iter().position(|&b| b == 0).unwrap_or(COMM_LEN);
        core::str::from_utf8(&self.comm[..end]).unwrap_or("")
    }

    /// The DNS query name as a string slice, trimmed at the first NUL. Returns
    /// an empty slice if the bytes are not valid UTF-8.
    pub fn qname_str(&self) -> &str {
        let end = self.qname.iter().position(|&b| b == 0).unwrap_or(QNAME_LEN);
        core::str::from_utf8(&self.qname[..end]).unwrap_or("")
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

    fn make_file(pid: u32, name: &str, path: &str) -> FileEvent {
        let mut comm = [0u8; COMM_LEN];
        let cb = name.as_bytes();
        let cn = cb.len().min(COMM_LEN);
        comm[..cn].copy_from_slice(&cb[..cn]);
        let mut path_buf = [0u8; PATH_LEN];
        let pb = path.as_bytes();
        let pn = pb.len().min(PATH_LEN);
        path_buf[..pn].copy_from_slice(&pb[..pn]);
        FileEvent {
            pid,
            comm,
            path: path_buf,
        }
    }

    fn file_to_bytes(ev: &FileEvent) -> Vec<u8> {
        let mut buf = Vec::with_capacity(FILE_EVENT_SIZE);
        buf.extend_from_slice(&ev.pid.to_ne_bytes());
        buf.extend_from_slice(&ev.comm);
        buf.extend_from_slice(&ev.path);
        buf
    }

    #[test]
    fn file_event_size_is_pid_comm_path() {
        assert_eq!(FILE_EVENT_SIZE, 4 + COMM_LEN + PATH_LEN);
    }

    #[test]
    fn file_from_bytes_round_trips_pid_comm_path() {
        let ev = make_file(4242, "pr-bot", "/etc/passwd");
        let parsed = FileEvent::from_bytes(&file_to_bytes(&ev)).expect("parse");
        assert_eq!(parsed.pid, ev.pid);
        assert_eq!(parsed.comm, ev.comm);
        assert_eq!(parsed.path, ev.path);
    }

    #[test]
    fn file_path_str_trims_at_nul() {
        let ev = make_file(1, "agent", "/var/lib/secret.json");
        assert_eq!(ev.path_str(), "/var/lib/secret.json");
        assert_eq!(ev.comm_str(), "agent");
    }

    #[test]
    fn file_from_bytes_rejects_short_slice() {
        assert!(FileEvent::from_bytes(&[0u8; FILE_EVENT_SIZE - 1]).is_none());
    }

    fn make_dns(pid: u32, name: &str, qname: &str) -> DnsEvent {
        let mut comm = [0u8; COMM_LEN];
        let cb = name.as_bytes();
        let cn = cb.len().min(COMM_LEN);
        comm[..cn].copy_from_slice(&cb[..cn]);
        let mut qname_buf = [0u8; QNAME_LEN];
        let qb = qname.as_bytes();
        let qn = qb.len().min(QNAME_LEN);
        qname_buf[..qn].copy_from_slice(&qb[..qn]);
        DnsEvent {
            pid,
            comm,
            qname: qname_buf,
        }
    }

    fn dns_to_bytes(ev: &DnsEvent) -> Vec<u8> {
        let mut buf = Vec::with_capacity(DNS_EVENT_SIZE);
        buf.extend_from_slice(&ev.pid.to_ne_bytes());
        buf.extend_from_slice(&ev.comm);
        buf.extend_from_slice(&ev.qname);
        buf
    }

    #[test]
    fn dns_event_size_is_pid_comm_qname() {
        assert_eq!(DNS_EVENT_SIZE, 4 + COMM_LEN + QNAME_LEN);
    }

    #[test]
    fn dns_from_bytes_round_trips_pid_comm_qname() {
        let ev = make_dns(4242, "pr-bot", "api.openai.com");
        let parsed = DnsEvent::from_bytes(&dns_to_bytes(&ev)).expect("parse");
        assert_eq!(parsed.pid, ev.pid);
        assert_eq!(parsed.comm, ev.comm);
        assert_eq!(parsed.qname, ev.qname);
    }

    #[test]
    fn dns_qname_str_trims_at_nul() {
        let ev = make_dns(1, "agent", "api.anthropic.com");
        assert_eq!(ev.qname_str(), "api.anthropic.com");
        assert_eq!(ev.comm_str(), "agent");
    }

    #[test]
    fn dns_from_bytes_rejects_short_slice() {
        assert!(DnsEvent::from_bytes(&[0u8; DNS_EVENT_SIZE - 1]).is_none());
    }
}
