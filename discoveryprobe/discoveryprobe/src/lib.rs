//! discoveryprobe -- userspace loader for the eBPF capture reference probe.
//!
//! Two halves, split by privilege and determinism:
//! - [`probe`]: PRIVILEGED (CAP_BPF). Loads the compiled BPF object, attaches
//!   the `sched_process_exec` tracepoint, and drains the ring buffer for a
//!   bounded window. Live, non-deterministic, runs only under the broker.
//! - [`mapping`]: PURE. Turns captured [`discoveryprobe_common::ExecEvent`]s into
//!   per-agent [`discoveryprobe_core::CaptureRecording`]s -- deterministic (I4) and
//!   unit-tested without privilege.
//!
//! The recording is the bridge contract consumed by `recette/surface/` (Python):
//! the probe proves RailNode SEES a simulated agent on the eBPF-wire surface,
//! even inside a Docker container.

pub mod mapping;
pub mod probe;

pub use mapping::{recordings_from_capture, recordings_from_execs, AgentProcessSpec};
pub use probe::{capture, Capture, CaptureConfig};
