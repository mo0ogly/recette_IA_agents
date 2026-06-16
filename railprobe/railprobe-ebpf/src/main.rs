#![no_std]
#![no_main]

//! railprobe eBPF capture program.
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
    helpers::{bpf_get_current_comm, bpf_get_current_pid_tgid},
    macros::{map, tracepoint},
    maps::RingBuf,
    programs::TracePointContext,
};
use railprobe_common::ExecEvent;

/// Ring buffer the userspace loader drains (256 KiB: power-of-two page multiple).
#[map]
static EXEC_EVENTS: RingBuf = RingBuf::with_byte_size(256 * 1024, 0);

#[tracepoint]
pub fn railprobe_exec(ctx: TracePointContext) -> u32 {
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

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    // eBPF has no unwinding; a panic in a verified program is unreachable.
    loop {}
}
