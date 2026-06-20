"""Tests for PublishingEventStore: durable-first ordering (I1) + fail-safe publish.

The decorator must (1) append to the durable inner store BEFORE diffusing to the
realtime transport, (2) never let a transport failure undo a committed append
(the event stays durable -- I1), and (3) delegate the read paths untouched. A
fake transport records or raises; no real bus is needed (deterministic, I4).
"""

from __future__ import annotations

import unittest

from recette.platform.eventstore.memory_store import InMemoryEventStore
from recette.platform.eventstore.protocol import StoredEvent
from recette.platform.realtime.protocol import Subscription
from recette.platform.realtime.publishing_store import PublishingEventStore


class _TransportBase:
    """RealtimeTransport conformance: only ``publish`` matters to these tests;
    ``subscribe``/``close`` are part of the protocol but never exercised here."""

    def subscribe(self) -> Subscription:
        raise NotImplementedError  # not used by the publishing-store tests

    def close(self) -> None:
        pass


class RecordingTransport(_TransportBase):
    """Captures every published event (best-effort transport, never raises)."""

    def __init__(self) -> None:
        self.published: list[dict] = []

    def publish(self, event: dict) -> None:
        self.published.append(event)


class RaisingTransport(_TransportBase):
    """A buggy transport that raises -- must not corrupt the append."""

    def __init__(self) -> None:
        self.calls = 0

    def publish(self, event: dict) -> None:
        self.calls += 1
        raise RuntimeError("bus down")


def _append(store: PublishingEventStore, n: int = 1) -> StoredEvent:
    return store.append(
        event_id=f"EV{n}",
        kind="action_executed",
        payload={"agent_id": "bot", "target_system": "okta", "action_type": "list_users"},
        schema_version="2.0",
    )


def _must(stored: StoredEvent | None) -> StoredEvent:
    assert stored is not None
    return stored


class TestPublishingEventStore(unittest.TestCase):
    def test_append_is_durable_then_published(self) -> None:
        inner = InMemoryEventStore()
        bus = RecordingTransport()
        store = PublishingEventStore(inner, bus)

        stored = _append(store)

        # Durable in the inner store (source of truth, I1)...
        self.assertEqual(_must(inner.get_by_event_id("EV1")).event_id, "EV1")
        # ...and diffused exactly once, carrying the stored event dict.
        self.assertEqual(len(bus.published), 1)
        self.assertEqual(bus.published[0]["event_id"], "EV1")
        self.assertEqual(bus.published[0]["seq"], stored.seq)

    def test_transport_failure_never_undoes_the_append(self) -> None:
        inner = InMemoryEventStore()
        bus = RaisingTransport()
        store = PublishingEventStore(inner, bus)

        stored = _append(store)  # must NOT raise despite the transport bug

        self.assertEqual(bus.calls, 1)
        # The event is still durable and the chain intact (I1) after a publish fail.
        self.assertEqual(_must(inner.get_by_event_id("EV1")).event_id, "EV1")
        self.assertEqual(stored.event_id, "EV1")
        self.assertTrue(inner.verify_chain().ok)

    def test_read_paths_delegate_to_inner(self) -> None:
        inner = InMemoryEventStore()
        store = PublishingEventStore(inner, RecordingTransport())

        _append(store, 1)
        _append(store, 2)

        self.assertEqual([e.event_id for e in store.read_from(0)], ["EV1", "EV2"])
        self.assertEqual(_must(store.get_by_event_id("EV2")).event_id, "EV2")
        self.assertTrue(store.verify_chain().ok)


if __name__ == "__main__":
    unittest.main()
