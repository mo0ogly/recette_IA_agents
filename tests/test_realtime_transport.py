"""G4 realtime transport: in-process fan-out, bounded-retry degradation, and
the PublishingEventStore decorator (store-first ordering, I1).

All deterministic and offline: the Phase 1 in-process transport is a real
pub/sub, no network, no NATS server. The chaos test proves the bus-degradation
failure mode (downstream down -> buffer + retry, never raises, store intact)."""

from __future__ import annotations

import unittest

from recette.platform.eventstore.memory_store import InMemoryEventStore
from recette.platform.realtime import (
    BoundedRetryBuffer,
    InProcessTransport,
    PublishingEventStore,
    RealtimeTransportConfigError,
    build_realtime_transport_from_env,
)

SCHEMA = "v1"


def _evt(n: int) -> dict:
    return {"seq": n, "event_id": f"EV{n:03d}", "kind": "action_executed"}


class InProcessTransportTest(unittest.TestCase):
    def test_publish_fans_out_to_all_subscribers(self) -> None:
        t = InProcessTransport()
        a = t.subscribe()
        b = t.subscribe()
        t.publish(_evt(1))
        self.assertEqual(a.get(timeout=1), _evt(1))
        self.assertEqual(b.get(timeout=1), _evt(1))
        a.close()
        b.close()

    def test_publish_with_no_subscribers_is_a_noop(self) -> None:
        InProcessTransport().publish(_evt(1))  # must not raise

    def test_closed_subscriber_stops_receiving(self) -> None:
        t = InProcessTransport()
        sub = t.subscribe()
        self.assertEqual(t.subscriber_count(), 1)
        sub.close()
        self.assertEqual(t.subscriber_count(), 0)
        t.publish(_evt(1))
        self.assertIsNone(sub.get(timeout=0.05))

    def test_close_is_idempotent(self) -> None:
        t = InProcessTransport()
        sub = t.subscribe()
        sub.close()
        sub.close()  # no raise

    def test_subscribe_after_transport_close_raises(self) -> None:
        t = InProcessTransport()
        t.close()
        with self.assertRaises(RuntimeError):
            t.subscribe()

    def test_slow_subscriber_drops_oldest_and_counts_lag(self) -> None:
        t = InProcessTransport(subscriber_buffer=2)
        sub = t.subscribe()
        for n in range(5):  # 5 events into a size-2 queue
            t.publish(_evt(n))
        self.assertEqual(sub.lagged, 3)
        # The two most recent survive, oldest evicted (FIFO drop-oldest).
        self.assertEqual(sub.get(timeout=1), _evt(3))
        self.assertEqual(sub.get(timeout=1), _evt(4))
        sub.close()

    def test_timeout_returns_none(self) -> None:
        sub = InProcessTransport().subscribe()
        self.assertIsNone(sub.get(timeout=0.01))
        sub.close()


class _FlakyTransport:
    """Inner transport whose publish fails while ``down`` is True."""

    def __init__(self) -> None:
        self.delivered: list[dict] = []
        self.down = False

    def publish(self, event: dict) -> None:
        if self.down:
            raise ConnectionError("downstream unreachable")
        self.delivered.append(event)

    def subscribe(self):  # pragma: no cover - not exercised here
        raise NotImplementedError

    def close(self) -> None:  # pragma: no cover - not exercised here
        pass


class BoundedRetryBufferTest(unittest.TestCase):
    def test_passthrough_when_downstream_healthy(self) -> None:
        inner = _FlakyTransport()
        buf = BoundedRetryBuffer(inner)
        buf.publish(_evt(1))
        self.assertEqual(inner.delivered, [_evt(1)])
        self.assertFalse(buf.degraded)
        self.assertEqual(buf.pending, 0)

    def test_chaos_downstream_down_buffers_never_raises(self) -> None:
        inner = _FlakyTransport()
        buf = BoundedRetryBuffer(inner)
        inner.down = True
        for n in range(3):
            buf.publish(_evt(n))  # must not raise
        self.assertTrue(buf.degraded)
        self.assertEqual(buf.pending, 3)
        self.assertEqual(inner.delivered, [])

    def test_recovery_drains_backlog_in_order(self) -> None:
        inner = _FlakyTransport()
        buf = BoundedRetryBuffer(inner)
        inner.down = True
        for n in range(3):
            buf.publish(_evt(n))
        inner.down = False
        self.assertEqual(buf.flush(), 0)
        self.assertEqual(inner.delivered, [_evt(0), _evt(1), _evt(2)])
        self.assertFalse(buf.degraded)

    def test_new_event_during_degradation_stays_behind_backlog(self) -> None:
        inner = _FlakyTransport()
        buf = BoundedRetryBuffer(inner)
        inner.down = True
        buf.publish(_evt(0))
        buf.publish(_evt(1))
        inner.down = False
        buf.publish(_evt(2))  # triggers a drain; order must be preserved
        self.assertEqual(inner.delivered, [_evt(0), _evt(1), _evt(2)])

    def test_bounded_capacity_evicts_oldest_and_counts(self) -> None:
        inner = _FlakyTransport()
        buf = BoundedRetryBuffer(inner, capacity=2)
        inner.down = True
        for n in range(5):
            buf.publish(_evt(n))
        self.assertEqual(buf.pending, 2)
        self.assertEqual(buf.dropped, 3)
        inner.down = False
        buf.flush()
        # Only the last two survived the bounded backlog (rest durable in store).
        self.assertEqual(inner.delivered, [_evt(3), _evt(4)])

    def test_capacity_must_be_positive(self) -> None:
        with self.assertRaises(ValueError):
            BoundedRetryBuffer(_FlakyTransport(), capacity=0)


class PublishingEventStoreTest(unittest.TestCase):
    def test_append_is_durable_then_published(self) -> None:
        store = InMemoryEventStore()
        transport = InProcessTransport()
        sub = transport.subscribe()
        decorated = PublishingEventStore(store, transport)
        stored = decorated.append(
            event_id="EV001",
            kind="action_executed",
            payload={"agent_id": "a"},
            schema_version=SCHEMA,
        )
        # Durable in the inner store (truth) ...
        self.assertEqual(store.get_by_event_id("EV001").event_id, "EV001")
        # ... and diffused with the exact stored envelope.
        self.assertEqual(sub.get(timeout=1), stored.to_dict())
        sub.close()

    def test_reads_delegate_transparently(self) -> None:
        store = InMemoryEventStore()
        decorated = PublishingEventStore(store, InProcessTransport())
        decorated.append(event_id="EV001", kind="action_denied", payload={}, schema_version=SCHEMA)
        self.assertEqual(len(decorated.read_from()), 1)
        self.assertIsNotNone(decorated.get_by_event_id("EV001"))
        self.assertTrue(decorated.verify_chain().ok)

    def test_publish_failure_never_undoes_the_append(self) -> None:
        class _RaisingTransport:
            def publish(self, event: dict) -> None:
                raise RuntimeError("transport bug")

            def subscribe(self):  # pragma: no cover
                raise NotImplementedError

            def close(self) -> None:  # pragma: no cover
                pass

        store = InMemoryEventStore()
        decorated = PublishingEventStore(store, _RaisingTransport())
        # append must still succeed and persist despite a misbehaving transport.
        stored = decorated.append(
            event_id="EV001", kind="action_executed", payload={}, schema_version=SCHEMA
        )
        self.assertEqual(stored.event_id, "EV001")
        self.assertIsNotNone(store.get_by_event_id("EV001"))


class FactoryTest(unittest.TestCase):
    def test_default_is_inproc(self) -> None:
        self.assertIsInstance(build_realtime_transport_from_env(), InProcessTransport)

    def test_inproc_explicit(self) -> None:
        import os

        prev = os.environ.get("INSPECT_IA_AGENTS_REALTIME")
        os.environ["INSPECT_IA_AGENTS_REALTIME"] = "INPROC"
        try:
            self.assertIsInstance(build_realtime_transport_from_env(), InProcessTransport)
        finally:
            if prev is None:
                del os.environ["INSPECT_IA_AGENTS_REALTIME"]
            else:
                os.environ["INSPECT_IA_AGENTS_REALTIME"] = prev

    def test_nats_without_url_raises_config_error(self) -> None:
        import os

        prev_b = os.environ.get("INSPECT_IA_AGENTS_REALTIME")
        prev_u = os.environ.get("INSPECT_IA_AGENTS_NATS_URL")
        os.environ["INSPECT_IA_AGENTS_REALTIME"] = "nats"
        os.environ.pop("INSPECT_IA_AGENTS_NATS_URL", None)
        try:
            with self.assertRaises(RealtimeTransportConfigError):
                build_realtime_transport_from_env()
        finally:
            _restore = (
                ("INSPECT_IA_AGENTS_REALTIME", prev_b),
                ("INSPECT_IA_AGENTS_NATS_URL", prev_u),
            )
            for k, v in _restore:
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_unknown_backend_raises(self) -> None:
        import os

        prev = os.environ.get("INSPECT_IA_AGENTS_REALTIME")
        os.environ["INSPECT_IA_AGENTS_REALTIME"] = "kafka"
        try:
            with self.assertRaises(RealtimeTransportConfigError):
                build_realtime_transport_from_env()
        finally:
            if prev is None:
                del os.environ["INSPECT_IA_AGENTS_REALTIME"]
            else:
                os.environ["INSPECT_IA_AGENTS_REALTIME"] = prev


if __name__ == "__main__":
    unittest.main()
