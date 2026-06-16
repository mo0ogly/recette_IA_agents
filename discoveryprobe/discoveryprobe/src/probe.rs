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
use aya::maps::RingBuf;
use aya::programs::TracePoint;
use aya::Ebpf;
use discoveryprobe_common::ExecEvent;

/// The tracepoint category and name the capture program attaches to.
const TRACEPOINT_CATEGORY: &str = "sched";
const TRACEPOINT_NAME: &str = "sched_process_exec";
/// The program and map symbols, matching `discoveryprobe-ebpf/src/main.rs`.
const PROGRAM: &str = "discoveryprobe_exec";
const RING_MAP: &str = "EXEC_EVENTS";

/// Where the compiled BPF object lives and how long to capture.
#[derive(Debug, Clone)]
pub struct CaptureConfig {
    /// Path to the `bpfel-unknown-none` object built by `discoveryprobe-ebpf`.
    pub object_path: PathBuf,
    /// Bounded capture window. Live capture is non-deterministic (I4 applies to
    /// the pure judge, not to this measurement).
    pub window: Duration,
}

/// Load + attach the capture program and collect exec events for the window.
///
/// PRIVILEGED (CAP_BPF). Returns every [`ExecEvent`] the kernel reported during
/// the window, in capture order; the pure [`crate::mapping`] turns them into
/// replay-stable recordings.
pub fn capture(config: &CaptureConfig) -> Result<Vec<ExecEvent>> {
    let object = std::fs::read(&config.object_path)
        .with_context(|| format!("read bpf object {}", config.object_path.display()))?;
    let mut bpf = Ebpf::load(&object).context("load bpf object")?;

    let program: &mut TracePoint = bpf
        .program_mut(PROGRAM)
        .with_context(|| format!("program {PROGRAM} not found in object"))?
        .try_into()
        .with_context(|| format!("{PROGRAM} is not a tracepoint"))?;
    program.load().context("load tracepoint program")?;
    program
        .attach(TRACEPOINT_CATEGORY, TRACEPOINT_NAME)
        .with_context(|| format!("attach {TRACEPOINT_CATEGORY}:{TRACEPOINT_NAME}"))?;

    let mut ring = RingBuf::try_from(
        bpf.map_mut(RING_MAP)
            .with_context(|| format!("map {RING_MAP} not found in object"))?,
    )
    .context("open ring buffer")?;

    let deadline = Instant::now() + config.window;
    let mut events = Vec::new();
    loop {
        while let Some(item) = ring.next() {
            if let Some(event) = ExecEvent::from_bytes(&item) {
                events.push(event);
            }
        }
        if Instant::now() >= deadline {
            break;
        }
        // The kernel ring buffer retains events between drains, so a short tick
        // within the bounded window loses nothing and needs no async runtime.
        std::thread::sleep(Duration::from_millis(5));
    }
    Ok(events)
}
