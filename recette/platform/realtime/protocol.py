"""RealtimeTransport protocol -- Data Plane fan-out of governed events.

The transport is NEVER the source of truth (I1): it carries a derived copy of
events already persisted in the append-only event store, so any drop is
recoverable by replaying the store. The transport only diffuses; it never
decides and never executes a side effect.

Defined before any implementation, like ``EventStore`` (event-store-decision.md):
Phase 1 default is the in-process transport (mono-host, real pub/sub); Phase 2
swaps in a NATS JetStream transport behind this same protocol.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

# A realtime payload is the StoredEvent envelope (``StoredEvent.to_dict()``).
# It is treated as opaque JSON-able data by the transport layer.
RealtimeEvent = dict


@runtime_checkable
class Subscription(Protocol):
    """A live consumer stream. Bounded per-subscriber: a slow consumer may lag
    (oldest dropped, lag counted) but never blocks the publisher -- the store
    remains the durable truth a lagging consumer can backfill from."""

    def get(self, timeout: float | None = None) -> RealtimeEvent | None:
        """Block up to ``timeout`` seconds for the next event. Return ``None``
        on timeout (lets an SSE loop emit a keepalive and check for disconnect)."""
        ...

    @property
    def lagged(self) -> int:
        """Count of events dropped for THIS subscriber due to a full buffer."""
        ...

    def close(self) -> None:
        """Detach from the transport. Idempotent."""
        ...


@runtime_checkable
class RealtimeTransport(Protocol):
    """Publish governed events and fan them out to live subscribers.

    ``publish`` is best-effort by contract: it must NEVER raise into the caller
    (the gateway/store), because the event is already durably persisted before
    publish is attempted. A degraded downstream is buffered and retried, never
    propagated as a failure of the governed action (failure-modes.md)."""

    def publish(self, event: RealtimeEvent) -> None:
        """Fan out one event. Never raises; downstream failures are absorbed."""
        ...

    def subscribe(self) -> Subscription:
        """Open a live subscription. The caller MUST ``close()`` it when done."""
        ...

    def close(self) -> None:
        """Release transport resources. Idempotent."""
        ...
