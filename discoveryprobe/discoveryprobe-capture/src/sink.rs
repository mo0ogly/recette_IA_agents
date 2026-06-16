//! Capture sink + bounded recorder.
//!
//! Migrates the callback-sink mechanism of cyberark/agentwatch
//! (`HookCallbackProto.on_hook_callback`) and the bounded in-memory ring of
//! tensorstax/agenttrace's `TraceManager` (mirrored on this project's existing
//! `RingTraceRecorder` idiom). A capture producer (the Rust wire/eBPF loader)
//! pushes [`LlmCallTrace`]s into a [`CaptureSink`]; [`RingCaptureRecorder`] is the
//! bounded, thread-safe implementation a run drains from.

use std::collections::VecDeque;
use std::sync::Mutex;

use crate::LlmCallTrace;

/// A sink that receives captured traces. Implementations MUST be fail-safe --
/// recording must never block or panic the capture path (observation never
/// breaks the run; eBPF stays the no-cooperation backstop).
pub trait CaptureSink {
    /// Record one captured trace.
    fn record(&self, trace: LlmCallTrace);
}

/// A bounded, thread-safe ring of the most recent captured traces.
///
/// Capacity caps memory: the oldest trace drops once full (the durable truth is
/// the audit log, I1; this buffer is jettable). Ordering is preserved.
#[derive(Debug)]
pub struct RingCaptureRecorder {
    inner: Mutex<VecDeque<LlmCallTrace>>,
    capacity: usize,
}

impl RingCaptureRecorder {
    /// Create a recorder holding at most `capacity` traces (must be > 0).
    pub fn with_capacity(capacity: usize) -> Self {
        let capacity = capacity.max(1);
        Self {
            inner: Mutex::new(VecDeque::with_capacity(capacity)),
            capacity,
        }
    }

    /// A snapshot of the recorded traces, oldest first.
    pub fn snapshot(&self) -> Vec<LlmCallTrace> {
        self.guard().iter().cloned().collect()
    }

    /// The number of traces currently held.
    pub fn len(&self) -> usize {
        self.guard().len()
    }

    /// Whether the recorder holds no trace.
    pub fn is_empty(&self) -> bool {
        self.guard().is_empty()
    }

    // Recover from a poisoned lock rather than panic: a producer thread that
    // panicked mid-record must not take the recorder (and the run) down with it.
    fn guard(&self) -> std::sync::MutexGuard<'_, VecDeque<LlmCallTrace>> {
        self.inner
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner())
    }
}

impl CaptureSink for RingCaptureRecorder {
    fn record(&self, trace: LlmCallTrace) {
        let mut ring = self.guard();
        if ring.len() == self.capacity {
            ring.pop_front();
        }
        ring.push_back(trace);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn trace(seq: u64) -> LlmCallTrace {
        LlmCallTrace {
            seq,
            event_id: format!("LC{seq:06}"),
            agent_id: "a1".to_string(),
            model: "m".to_string(),
            kind: "tool_call".to_string(),
            tool_name: Some("read_repo".to_string()),
            resource: "acme/x".to_string(),
            prompt_tokens: 1,
            completion_tokens: 1,
            latency_ms: 5,
            error: None,
        }
    }

    #[test]
    fn records_in_order() {
        let recorder = RingCaptureRecorder::with_capacity(8);
        recorder.record(trace(1));
        recorder.record(trace(2));
        let seqs: Vec<u64> = recorder.snapshot().iter().map(|t| t.seq).collect();
        assert_eq!(seqs, vec![1, 2]);
    }

    #[test]
    fn drops_oldest_when_over_capacity() {
        let recorder = RingCaptureRecorder::with_capacity(2);
        recorder.record(trace(1));
        recorder.record(trace(2));
        recorder.record(trace(3));
        let seqs: Vec<u64> = recorder.snapshot().iter().map(|t| t.seq).collect();
        assert_eq!(seqs, vec![2, 3]);
    }

    #[test]
    fn zero_capacity_is_coerced_to_one() {
        let recorder = RingCaptureRecorder::with_capacity(0);
        recorder.record(trace(1));
        recorder.record(trace(2));
        assert_eq!(recorder.len(), 1);
    }
}
