#![no_std]
#![no_main]

//! discoveryprobe eBPF capture program.
//!
//! Attaches to the `sched:sched_process_exec` tracepoint (more stable across
//! kernel versions than the raw `execve` syscall tracepoint). For every process
//! exec it captures the pid and command name -- the kernel's evidence that an
//! agent process is running -- and pushes one [`ExecEvent`] into a ring buffer
//! the userspace loader drains. Because the host kernel sees every container's
//! processes (one shared kernel), this captures a Dockerised simulated agent
//! without any in-process hook: the eBPF-wire surface.
//!
//! Privilege: this program only RUNS once loaded and attached by the privileged
//! broker (CAP_BPF). Compiling it (what this crate proves unprivileged) does not
//! load or attach anything.

use aya_ebpf::{
    helpers::{bpf_get_current_comm, bpf_get_current_pid_tgid, bpf_probe_read_user},
    macros::{map, tracepoint},
    maps::RingBuf,
    programs::TracePointContext,
};
use discoveryprobe_common::{ConnectEvent, ExecEvent};

/// Ring buffer the userspace loader drains (256 KiB: power-of-two page multiple).
#[map]
static EXEC_EVENTS: RingBuf = RingBuf::with_byte_size(256 * 1024, 0);

/// Ring buffer for outbound connect events, drained by the same loader.
#[map]
static CONNECT_EVENTS: RingBuf = RingBuf::with_byte_size(256 * 1024, 0);

/// `AF_INET` -- IPv4 socket family (the only family captured for now).
const AF_INET: u16 = 2;

/// Byte offset of the `struct sockaddr * uservaddr` argument in the
/// `syscalls:sys_enter_connect` tracepoint record. Stable syscall-enter layout:
/// common header `0..8`, `__syscall_nr` at `8`, then args from `16` (fd@16,
/// uservaddr@24, addrlen@32). Verified against the kernel tracepoint `format`
/// (root-gated on this host); see docs/migration-provenance.md for the source.
const USERVADDR_OFFSET: usize = 24;

#[tracepoint]
pub fn discoveryprobe_exec(ctx: TracePointContext) -> u32 {
    // A failed capture (full ring buffer, comm read error) drops the event
    // rather than disturbing the traced process -- the probe is passive.
    let _ = try_capture(&ctx);
    0
}

fn try_capture(_ctx: &TracePointContext) -> Result<(), ()> {
    // reserve -> write -> submit, the canonical aya RingBuf idiom
    // (aya test/integration-ebpf/src/ring_buf.rs). `write` initialises the
    // reserved MaybeUninit in place, so no unsafe pointer juggling is needed.
    let mut entry = EXEC_EVENTS.reserve::<ExecEvent>(0).ok_or(())?;
    let pid = (bpf_get_current_pid_tgid() >> 32) as u32;
    let comm = bpf_get_current_comm().map_err(|_| ())?;
    entry.write(ExecEvent { pid, comm });
    entry.submit(0);
    Ok(())
}

#[tracepoint]
pub fn discoveryprobe_connect(ctx: TracePointContext) -> u32 {
    // Passive: any read/reserve failure drops the event, never disturbs the
    // traced process.
    let _ = try_capture_connect(&ctx);
    0
}

fn try_capture_connect(ctx: &TracePointContext) -> Result<(), i64> {
    // The agent's outbound TCP connect -- for an LLM agent, the HTTPS dial to
    // the provider. agentwatch sees this in-process at httpcore; here we see it
    // at the kernel, without the agent's cooperation (catches a hook-blind
    // ghost). Read the userspace `sockaddr` pointer from the tracepoint record,
    // then probe-read its sockaddr_in fields.
    // SAFETY: `read_at` reads a fixed-size pointer field at a verifier-checked
    // offset within the tracepoint record the kernel itself populated; the
    // offset is within the record bounds for sys_enter_connect.
    let uservaddr = unsafe { ctx.read_at::<*const u8>(USERVADDR_OFFSET)? };
    if uservaddr.is_null() {
        return Err(0);
    }
    // sockaddr_in layout: sin_family u16 @0, sin_port u16 (network order) @2,
    // sin_addr u32 (network order) @4.
    // SAFETY: `bpf_probe_read_user` is the kernel-sanctioned fallible read of
    // userspace memory from an eBPF program -- a bad/unmapped address returns
    // Err (propagated by `?`) instead of faulting, so dereferencing the user
    // `sockaddr` pointer is sound.
    let family = unsafe { bpf_probe_read_user::<u16>(uservaddr as *const u16)? };
    if family != AF_INET {
        // IPv4 only for now; other families are dropped (documented boundary).
        return Err(0);
    }
    // SAFETY: same as above -- a fallible userspace read at the sin_port (+2)
    // offset within the sockaddr_in; an out-of-bounds read returns Err.
    let port = unsafe { bpf_probe_read_user::<u16>(uservaddr.wrapping_add(2) as *const u16)? };
    // SAFETY: same as above -- a fallible userspace read at the sin_addr (+4)
    // offset within the sockaddr_in; an out-of-bounds read returns Err.
    let addr = unsafe { bpf_probe_read_user::<u32>(uservaddr.wrapping_add(4) as *const u32)? };

    let pid = (bpf_get_current_pid_tgid() >> 32) as u32;
    let comm = bpf_get_current_comm()?;

    let mut entry = CONNECT_EVENTS.reserve::<ConnectEvent>(0).ok_or(0_i64)?;
    // `to_ne_bytes` preserves the exact in-memory (network-order) bytes the
    // kernel read, so userspace parses octets in order and the port big-endian.
    entry.write(ConnectEvent {
        pid,
        daddr: addr.to_ne_bytes(),
        dport: port.to_ne_bytes(),
        _pad: [0_u8; 2],
        comm,
    });
    entry.submit(0);
    Ok(())
}

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    // eBPF has no unwinding; a panic in a verified program is unreachable.
    loop {}
}
