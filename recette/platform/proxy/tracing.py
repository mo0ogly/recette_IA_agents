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

The concrete recorder is ``SqliteTraceRecorder`` (store.py), a facade over the
SQLite-backed ``SqliteProxyStore``; this module keeps the ``ProxyTrace`` model,
the ``TraceRecorder`` protocol, and the ``TracingProxy`` decorator.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from ..events import PlatformActionEvent
from .protocol import ExecutionResult, ExternalSystemProxy

DEBUG_ENV = "INSPECT_IA_AGENTS_PROXY_DEBUG"


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
    # The resolved server name (fqdn) the side effect was routed to, for trace
    # realism (reads ``api.github.com`` instead of ``127.0.0.1:9101``). Falls
    # back to ``target_system`` when no name was resolved (back-compat). Required
    # (str, never None) by construction: ``SqliteTraceRecorder.record`` falls back
    # to ``event.target_system`` (always a non-empty str), unlike the optional
    # ``ExecutionResult.target: str | None``.
    target: str
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
            "target": self.target,
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

    def set_enabled(self, value: bool) -> None:
        """Flip recording at runtime (operator toggle from the console).

        Recording is a debug view over the I5 boundary; toggling it changes only
        whether traces are buffered, never the decision path (I4)."""
        self._enabled = bool(value)

    def execute(self, event: PlatformActionEvent) -> ExecutionResult:
        result = self._inner.execute(event)
        if self._enabled:
            try:
                self._recorder.record(event, result, run_id=self._run_id)
            except Exception:  # noqa: BLE001 - recording must never break execution
                pass
        return result
