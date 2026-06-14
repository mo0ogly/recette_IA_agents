"""InProcessTransport -- Phase 1 realtime transport (mono-host, real pub/sub).

This is a genuine working transport, not a stub: it fans out every published
event to all live subscribers via thread-safe bounded queues. It mirrors the
SQLite-first phasing of the event store (event-store-decision.md): a real,
single-host implementation that the Phase 2 NATS transport later replaces
behind the same ``RealtimeTransport`` protocol.

Bounded per subscriber (I1-safe): a slow consumer's queue drops its OLDEST
event and increments a lag counter rather than growing without bound or
blocking the publisher. No event is lost to the system -- the dropped copy is
still in the durable event store and replayable. The publisher side never
blocks on a slow consumer.
"""

from __future__ import annotations

import queue
import threading

from .protocol import RealtimeEvent

DEFAULT_SUBSCRIBER_BUFFER = 1024


class _Subscription:
    """One live consumer backed by a bounded FIFO queue."""

    def __init__(self, transport: InProcessTransport, maxsize: int) -> None:
        self._transport = transport
        self._queue: queue.Queue[RealtimeEvent] = queue.Queue(maxsize=maxsize)
        self._lagged = 0
        self._closed = False

    def _offer(self, event: RealtimeEvent) -> None:
        """Non-blocking enqueue; drop-oldest on overflow (slow consumer)."""
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            try:
                self._queue.get_nowait()  # evict oldest
                self._lagged += 1
                self._queue.put_nowait(event)
            except queue.Empty:  # pragma: no cover - racing drain, event still offered
                self._queue.put_nowait(event)

    def get(self, timeout: float | None = None) -> RealtimeEvent | None:
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    @property
    def lagged(self) -> int:
        return self._lagged

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._transport._remove(self)


class InProcessTransport:
    """Thread-safe in-process fan-out transport (Phase 1 default)."""

    def __init__(self, *, subscriber_buffer: int = DEFAULT_SUBSCRIBER_BUFFER) -> None:
        self._subscriber_buffer = subscriber_buffer
        self._subscribers: set[_Subscription] = set()
        self._lock = threading.Lock()
        self._closed = False

    def publish(self, event: RealtimeEvent) -> None:
        # Snapshot under lock, fan out outside the lock so a slow consumer's
        # enqueue never holds the publisher path. Never raises (contract).
        with self._lock:
            targets = tuple(self._subscribers)
        for sub in targets:
            sub._offer(event)

    def subscribe(self) -> _Subscription:
        sub = _Subscription(self, self._subscriber_buffer)
        with self._lock:
            if self._closed:
                raise RuntimeError("transport is closed")
            self._subscribers.add(sub)
        return sub

    def _remove(self, sub: _Subscription) -> None:
        with self._lock:
            self._subscribers.discard(sub)

    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._subscribers.clear()
