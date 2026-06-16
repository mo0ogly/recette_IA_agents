//! Privileged capture: load + attach the eBPF program and drain its ring buffer.
//!
//! Uses the canonical aya idiom (aya `aya/src/maps/ring_buf.rs` doc example and
//! `TracePoint::load`/`attach`): load the object, get the tracepoint program,
//! `load()` + `attach(category, name)`, then poll `RingBuf::next` until the
//! bounded window elapses.
//!
//! PRIVILEGED: loading and attaching a BPF program requires CAP_BPF. This runs
//! only under the broker; the host `cargo test` exercises [`crate::mapping`],
//! not this path.

use std::path::PathBuf;
use std::time::{Duration, Instant};

use anyhow::{Context, Result};
use aya::maps::{MapData, RingBuf};
use aya::programs::TracePoint;
use aya::Ebpf;
use discoveryprobe_common::{ConnectEvent, ExecEvent};

/// The exec tracepoint the exec-capture program attaches to.
const EXEC_CATEGORY: &str = "sched";
const EXEC_NAME: &str = "sched_process_exec";
/// The connect tracepoint the egress-capture program attaches to.
const CONNECT_CATEGORY: &str = "syscalls";
const CONNECT_NAME: &str = "sys_enter_connect";
/// The program and map symbols, matching `discoveryprobe-ebpf/src/main.rs`.
const EXEC_PROGRAM: &str = "discoveryprobe_exec";
const CONNECT_PROGRAM: &str = "discoveryprobe_connect";
const EXEC_RING_MAP: &str = "EXEC_EVENTS";
const CONNECT_RING_MAP: &str = "CONNECT_EVENTS";

/// Where the compiled BPF object lives and how long to capture.
#[derive(Debug, Clone)]
pub struct CaptureConfig {
    /// Path to the `bpfel-unknown-none` object built by `discoveryprobe-ebpf`.
    pub object_path: PathBuf,
    /// Bounded capture window. Live capture is non-deterministic (I4 applies to
    /// the pure judge, not to this measurement).
    pub window: Duration,
}

/// One window of kernel observations: process execs and outbound connects.
///
/// The two surfaces of the kernel probe, captured together and reconciled into
/// a single `ebpf_wire` recording by [`crate::recordings_from_capture`].
#[derive(Debug, Clone, Default)]
pub struct Capture {
    /// Process-exec events (the agent ran).
    pub execs: Vec<ExecEvent>,
    /// Outbound TCP connect events (the agent dialed out, e.g. an LLM provider).
    pub connects: Vec<ConnectEvent>,
}

/// Load + attach both capture programs and collect their events for the window.
///
/// PRIVILEGED (CAP_BPF). Returns every [`ExecEvent`] and [`ConnectEvent`] the
/// kernel reported during the window, in capture order; the pure
/// [`crate::mapping`] turns them into replay-stable recordings.
pub fn capture(config: &CaptureConfig) -> Result<Capture> {
    let object = std::fs::read(&config.object_path)
        .with_context(|| format!("read bpf object {}", config.object_path.display()))?;
    let mut bpf = Ebpf::load(&object).context("load bpf object")?;

    attach_tracepoint(&mut bpf, EXEC_PROGRAM, EXEC_CATEGORY, EXEC_NAME)?;
    attach_tracepoint(&mut bpf, CONNECT_PROGRAM, CONNECT_CATEGORY, CONNECT_NAME)?;

    // Take ownership of each ring map so both can be drained in one loop (a
    // single `map_mut` borrow could not hold two rings at once). The attached
    // programs stay live because `bpf` is kept in scope until the function ends.
    let mut exec_ring = take_ring(&mut bpf, EXEC_RING_MAP)?;
    let mut connect_ring = take_ring(&mut bpf, CONNECT_RING_MAP)?;

    let deadline = Instant::now() + config.window;
    let mut capture = Capture::default();
    loop {
        while let Some(item) = exec_ring.next() {
            if let Some(event) = ExecEvent::from_bytes(&item) {
                capture.execs.push(event);
            }
        }
        while let Some(item) = connect_ring.next() {
            if let Some(event) = ConnectEvent::from_bytes(&item) {
                capture.connects.push(event);
            }
        }
        if Instant::now() >= deadline {
            break;
        }
        // The kernel ring buffer retains events between drains, so a short tick
        // within the bounded window loses nothing and needs no async runtime.
        std::thread::sleep(Duration::from_millis(5));
    }
    Ok(capture)
}

/// Load and attach one tracepoint program by symbol/category/name.
fn attach_tracepoint(bpf: &mut Ebpf, program: &str, category: &str, name: &str) -> Result<()> {
    let prog: &mut TracePoint = bpf
        .program_mut(program)
        .with_context(|| format!("program {program} not found in object"))?
        .try_into()
        .with_context(|| format!("{program} is not a tracepoint"))?;
    prog.load()
        .with_context(|| format!("load tracepoint program {program}"))?;
    prog.attach(category, name)
        .with_context(|| format!("attach {category}:{name}"))?;
    Ok(())
}

/// Take ownership of a ring-buffer map out of the loaded object.
fn take_ring(bpf: &mut Ebpf, name: &str) -> Result<RingBuf<MapData>> {
    let map = bpf
        .take_map(name)
        .with_context(|| format!("map {name} not found in object"))?;
    RingBuf::try_from(map).with_context(|| format!("open ring buffer {name}"))
}
