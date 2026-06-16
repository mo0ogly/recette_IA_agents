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
}
