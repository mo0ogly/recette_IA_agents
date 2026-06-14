"""BoundedRetryBuffer -- failure-mode wrapper for a fallible transport.

Wraps an inner ``RealtimeTransport`` whose ``publish`` may fail (a network
transport like NATS). It enforces the bus-degradation failure mode
(failure-modes.md): when the downstream is unreachable, events are held in a
BOUNDED in-memory backlog and retried, and ``publish`` NEVER raises into the
caller. No external action is executed by the transport, so a degraded bus
cannot trigger a side effect.

"No event loss" is guaranteed by the durable event store (I1), not by this
buffer: every buffered event is already persisted, so an overflow eviction
drops only a derived realtime copy (counted), recoverable by store replay.
Order is preserved -- the backlog is drained FIFO and a new event published
while a backlog exists is queued behind it, never ahead.
"""

from __future__ import annotations

import collections
import logging
import threading
from typing import Protocol

from .protocol import RealtimeEvent, Subscription

_log = logging.getLogger("inspect_ia_agents.realtime.buffer")

DEFAULT_CAPACITY = 4096


class _FallibleTransport(Protocol):
    """Structural type of the wrapped transport (publish may raise)."""

    def publish(self, event: RealtimeEvent) -> None: ...
    def subscribe(self) -> Subscription: ...
    def close(self) -> None: ...


class BoundedRetryBuffer:
    """Absorb downstream failures: bounded backlog + FIFO retry, never raises."""

    def __init__(self, inner: _FallibleTransport, *, capacity: int = DEFAULT_CAPACITY) -> None:
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        self._inner = inner
        self._capacity = capacity
        self._backlog: collections.deque[RealtimeEvent] = collections.deque()
        self._dropped = 0
        self._degraded = False
        self._lock = threading.Lock()

    def publish(self, event: RealtimeEvent) -> None:
        with self._lock:
            if self._backlog:
                # Downstream already degraded: preserve order, queue behind the
                # backlog, then attempt a drain. Never send the new event ahead.
                self._enqueue(event)
                self._drain_locked()
                return
            try:
                self._inner.publish(event)
            except Exception as exc:  # downstream unreachable -> buffer, never raise
                self._degraded = True
                _log.warning("realtime downstream failed, buffering event: %s", exc)
                self._enqueue(event)

    def flush(self) -> int:
        """Retry the backlog FIFO. Returns the number still pending afterwards.
        Call from a scheduler/heartbeat to drain a recovered downstream."""
        with self._lock:
            self._drain_locked()
            return len(self._backlog)

    def _drain_locked(self) -> None:
        while self._backlog:
            event = self._backlog[0]
            try:
                self._inner.publish(event)
            except Exception:  # still down: stop, keep order, stay degraded
                return
            self._backlog.popleft()
        if self._degraded:
            self._degraded = False
            _log.info("realtime downstream recovered, backlog drained")

    def _enqueue(self, event: RealtimeEvent) -> None:
        if len(self._backlog) >= self._capacity:
            self._backlog.popleft()  # evict oldest; copy still durable in the store
            self._dropped += 1
        self._backlog.append(event)

    def subscribe(self) -> Subscription:
        return self._inner.subscribe()

    def close(self) -> None:
        self._inner.close()

    @property
    def pending(self) -> int:
        with self._lock:
            return len(self._backlog)

    @property
    def dropped(self) -> int:
        with self._lock:
            return self._dropped

    @property
    def degraded(self) -> bool:
        with self._lock:
            return self._degraded
