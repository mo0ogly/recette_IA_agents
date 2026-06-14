"""Debug tracing for the side-effect proxy path (I5 observability).

A ``TracingProxy`` decorates ANY ``ExternalSystemProxy`` (lab or real) and records
one ``ProxyTrace`` per ``execute()`` -- the request intent (event fields) plus the
outcome (status, side_effect_hash, error). It is a pure decorator: it never changes
the wrapped proxy's result and never raises on a recording failure (fail-safe,
failure-modes.md). Recording is parametrable via ``enabled`` (off => zero overhead,
the wrapped proxy is called directly).

Determinism (I4): a trace carries no wall-clock value. Ordering comes from a monotone
``seq`` assigned by the recorder; ``timestamp`` is the event's already-captured logical
clock (a deterministic input, never ``now()``). So a replayed stream produces an
identical trace sequence.

Immutability (I1): traces are a read-only VIEW over execution. They never mutate the
audit log; the recorder is a bounded, jettable buffer (rebuildable from the log).
"""

from __future__ import annotations

import os
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from ..events import PlatformActionEvent
from .protocol import ExecutionResult, ExternalSystemProxy

DEBUG_ENV = "INSPECT_IA_AGENTS_PROXY_DEBUG"
DEFAULT_RING_CAPACITY = 512


def debug_enabled_from_env() -> bool:
    """Read the debug toggle from the environment (R5: no hardcoded flag).

    Truthy values: ``1``, ``true``, ``yes``, ``on`` (case-insensitive). Anything
    else, or unset, is off.
    """
    raw = os.environ.get(DEBUG_ENV, "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class ProxyTrace:
    """One recorded side-effect execution (request intent + outcome)."""

    seq: int
    event_id: str
    timestamp: str
    agent_id: str
    target_system: str
    action_type: str
    resource: str
    request_payload: dict
    ok: bool
    status_code: int
    side_effect_hash: str | None
    error: str | None
    # Operational link to the originating run (F3). It is run metadata, not an
    # AgentActionEvent field, so it lives on the trace (the view), never on the
    # canonical event or the audit log (I1). None for traces with no run context.
    run_id: str | None = None
    # The server's response body (the other half of the exchange). The request
    # is `request_payload`; this is what the target system answered, so the
    # console can show the full agent <-> server round-trip, not just the status.
    response: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "seq": self.seq,
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "agent_id": self.agent_id,
            "target_system": self.target_system,
            "action_type": self.action_type,
            "resource": self.resource,
            "request_payload": self.request_payload,
            "ok": self.ok,
            "status_code": self.status_code,
            "side_effect_hash": self.side_effect_hash,
            "error": self.error,
            "run_id": self.run_id,
            "response": self.response,
        }


@runtime_checkable
class TraceRecorder(Protocol):
    """Sink for proxy traces. ``record`` MUST NOT raise (fail-safe)."""

    def record(
        self, event: PlatformActionEvent, result: ExecutionResult, run_id: str | None = None
    ) -> None: ...

    def snapshot(self) -> list[ProxyTrace]: ...


class RingTraceRecorder:
    """Bounded, thread-safe in-memory ring of the most recent traces.

    ``capacity`` caps memory (oldest traces drop, I1 keeps the durable truth in the
    audit log -- this buffer is jettable). ``seq`` is monotone across the recorder's
    life so trace ordering is stable even after the ring has wrapped.
    """

    def __init__(self, capacity: int = DEFAULT_RING_CAPACITY) -> None:
        if capacity <= 0:
            raise ValueError("RingTraceRecorder capacity must be positive")
        self._ring: deque[ProxyTrace] = deque(maxlen=capacity)
        self._seq = 0
        self._lock = threading.Lock()

    def record(
        self, event: PlatformActionEvent, result: ExecutionResult, run_id: str | None = None
    ) -> None:
        with self._lock:
            self._seq += 1
            trace = ProxyTrace(
                seq=self._seq,
                event_id=event.event_id,
                timestamp=event.timestamp,
                agent_id=event.agent_id,
                target_system=event.target_system,
                action_type=event.action_type,
                resource=event.resource,
                request_payload=dict(event.payload),
                ok=result.ok,
                status_code=result.status_code,
                side_effect_hash=result.side_effect_hash,
                error=result.error,
                run_id=run_id,
                response=dict(result.response),
            )
            self._ring.append(trace)

    def snapshot(self) -> list[ProxyTrace]:
        with self._lock:
            return list(self._ring)

    def clear(self) -> None:
        with self._lock:
            self._ring.clear()


class TracingProxy:
    """Decorator that records each side effect through ``recorder`` when enabled.

    The wrapped proxy's ``ExecutionResult`` is returned verbatim; tracing never alters
    governance behaviour. A recording exception is swallowed (fail-safe): observability
    must never break the I5 execution path.
    """

    def __init__(
        self,
        inner: ExternalSystemProxy,
        recorder: TraceRecorder,
        *,
        enabled: bool = True,
        run_id: str | None = None,
    ) -> None:
        self._inner = inner
        self._recorder = recorder
        self._enabled = enabled
        self._run_id = run_id

    @property
    def enabled(self) -> bool:
        return self._enabled

    def execute(self, event: PlatformActionEvent) -> ExecutionResult:
        result = self._inner.execute(event)
        if self._enabled:
            try:
                self._recorder.record(event, result, run_id=self._run_id)
            except Exception:  # noqa: BLE001 - recording must never break execution
                pass
        return result
