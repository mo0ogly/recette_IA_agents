#![no_std]
#![no_main]

//! Minimal eBPF capture PoC: a tracepoint on the `execve` syscall.
//!
//! This is the de-risking program -- it proves the nightly + build-std +
//! bpf-linker path compiles a valid BPF object. It will grow to push captured
//! events (pid, comm, dest addr) to a perf/ring map for the userspace probe.

use aya_ebpf::{macros::tracepoint, programs::TracePointContext};

#[tracepoint]
pub fn execve(_ctx: TracePointContext) -> u32 {
    0
}

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    // eBPF has no unwinding; a panic in a verified program is unreachable.
    loop {}
}
