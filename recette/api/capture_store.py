"""In-memory per-run capture store for LlmCallTraces.

Mirrors ``RingTraceRecorder`` (bounded, thread-safe): the durable truth is the
audit log (I1); this ring is a jettable view the Probe UX reads. A run's
``capture_sink`` (the wrapped ``CapturingLlm``) appends here; ``GET
/capture/llm-traces`` reads it back. Unknown run -> empty list (fail-safe).
"""

from __future__ import annotations

import threading
from collections import defaultdict, deque
from collections.abc import Callable

from ..capture.llm_trace import LlmCallTrace

DEFAULT_CAPACITY = 1000


class CaptureStore:
    """Per-run bounded rings of captured LLM traces."""

    def __init__(self, capacity: int = DEFAULT_CAPACITY) -> None:
        if capacity <= 0:
            raise ValueError("CaptureStore capacity must be positive")
        self._capacity = capacity
        self._rings: dict[str, deque[LlmCallTrace]] = defaultdict(lambda: deque(maxlen=capacity))
        self._lock = threading.Lock()

    def record(self, run_id: str, trace: LlmCallTrace) -> None:
        with self._lock:
            self._rings[run_id].append(trace)

    def sink_for(self, run_id: str) -> Callable[[LlmCallTrace], None]:
        """A capture sink bound to one run (pass as ``capture_sink``)."""
        return lambda trace: self.record(run_id, trace)

    def traces(self, run_id: str) -> list[dict]:
        with self._lock:
            return [t.to_dict() for t in self._rings.get(run_id, ())]

    def all_traces(self) -> list[LlmCallTrace]:
        """Every captured trace across all runs (for the metrics aggregate),
        ordered by run then capture order. A bounded snapshot (rings are
        capacity-capped); read-only."""
        with self._lock:
            return [trace for ring in self._rings.values() for trace in ring]
