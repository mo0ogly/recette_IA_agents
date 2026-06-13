"""PublishingEventStore -- decorate an EventStore to fan out appends (I1).

Mirrors the ``TracingProxy`` decorator pattern: it wraps any ``EventStore`` and,
after a successful ``append`` to the durable log, publishes the stored event to
a ``RealtimeTransport``. Ordering is the invariant guarantee: the event is
DURABLE (in the store, I1) before it is ever diffused, so the store is always
the source of truth and the realtime copy is derived and replayable.

The decorator is transparent: ``read_from``/``get_by_event_id``/``verify_chain``
delegate untouched, and ``append`` returns the inner result unchanged. A publish
failure can never corrupt or undo the append -- the transport contract is
best-effort and ``publish`` never raises (see BoundedRetryBuffer / InProcessTransport).
"""

from __future__ import annotations

import logging

from ..eventstore.protocol import ChainReport, EventStore, StoredEvent
from .protocol import RealtimeTransport

_log = logging.getLogger("agentrail.realtime.publishing_store")


class PublishingEventStore:
    """EventStore decorator that diffuses each append to a RealtimeTransport."""

    def __init__(self, inner: EventStore, transport: RealtimeTransport) -> None:
        self._inner = inner
        self._transport = transport

    def append(
        self, *, event_id: str, kind: str, payload: dict, schema_version: str
    ) -> StoredEvent:
        # Durable first (I1): the store is the truth. Only then diffuse.
        stored = self._inner.append(
            event_id=event_id, kind=kind, payload=payload, schema_version=schema_version
        )
        # Defensive: the transport contract forbids raising, but a third-party
        # transport bug must never undo a committed append. Absorb and log.
        try:
            self._transport.publish(stored.to_dict())
        except Exception as exc:  # pragma: no cover - contract says transport never raises
            _log.error("realtime publish raised (event already durable, ignoring): %s", exc)
        return stored

    def read_from(
        self,
        seq: int = 0,
        *,
        limit: int | None = None,
        tail: int | None = None,
        agent_id: str | None = None,
        target_system: str | None = None,
        kind: str | None = None,
    ) -> list[StoredEvent]:
        return self._inner.read_from(
            seq,
            limit=limit,
            tail=tail,
            agent_id=agent_id,
            target_system=target_system,
            kind=kind,
        )

    def get_by_event_id(self, event_id: str) -> StoredEvent | None:
        return self._inner.get_by_event_id(event_id)

    def verify_chain(self) -> ChainReport:
        return self._inner.verify_chain()
