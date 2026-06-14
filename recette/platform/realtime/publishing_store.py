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
from ..observability import log_correlated
from .protocol import RealtimeTransport

_log = logging.getLogger("inspect_ia_agents.realtime.publishing_store")
# Forensic audit channel (R6): one correlated record per governed event, keyed by
# event_id so an auditor can reconstruct a full action flow from the logs alone.
_audit_log = logging.getLogger("inspect_ia_agents.audit")


def _agent_id_of(stored: StoredEvent) -> str | None:
    value = stored.payload.get("agent_id")
    return value if isinstance(value, str) else None


def _correlation_fields(stored: StoredEvent) -> dict[str, object]:
    """Pull the non-identity correlation keys off a stored event payload
    (best-effort: a slim payload simply yields fewer fields). agent_id is read
    separately by ``_agent_id_of`` so it stays typed."""
    payload = stored.payload
    decision = payload.get("policy_decision")
    verdict = decision.get("verdict") if isinstance(decision, dict) else None
    return {
        "kind": stored.kind,
        "verdict": verdict,
        "target_system": payload.get("target_system"),
        "action_type": payload.get("action_type"),
        "correlates_event_id": payload.get("correlates_event_id"),
    }


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
        # Forensic correlation (R6): emit one structured record keyed by event_id
        # before diffusing, so the audit log alone can reconstruct the flow.
        log_correlated(
            _audit_log,
            logging.INFO,
            "governed event appended",
            event_id=stored.event_id,
            agent_id=_agent_id_of(stored),
            **_correlation_fields(stored),
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
