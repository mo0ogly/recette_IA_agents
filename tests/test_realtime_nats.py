"""G4 NATS JetStream transport -- verified against a REAL NATS server.

Skipped unless both nats-py is installed AND AGENTRAIL_TEST_NATS_URL points at a
JetStream-enabled server (e.g. ``docker run -p 14222:4222 nats:2.10 -js`` ->
AGENTRAIL_TEST_NATS_URL=nats://127.0.0.1:14222). The default offline suite never
needs a broker; the in-process transport covers the deterministic path."""

from __future__ import annotations

import os
import time
import unittest

try:
    import nats  # noqa: F401

    _HAS_NATS = True
except ImportError:
    _HAS_NATS = False

_URL = os.environ.get("AGENTRAIL_TEST_NATS_URL")


def _evt(n: int) -> dict:
    return {"seq": n, "event_id": f"EV{n:03d}", "kind": "action_executed"}


@unittest.skipUnless(_HAS_NATS and _URL, "needs nats-py + AGENTRAIL_TEST_NATS_URL")
class NatsJetStreamTransportTest(unittest.TestCase):
    def setUp(self) -> None:
        from recette.platform.realtime.nats_transport import NatsJetStreamTransport

        # Unique subject AND stream per test so leftover state never bleeds in.
        tag = int(time.time() * 1000)
        subject = f"agentrail.test.{tag}"
        stream = f"AGENTRAIL_TEST_{tag}"
        self.transport = NatsJetStreamTransport(_URL, subject=subject, stream=stream)
        self.addCleanup(self.transport.close)

    def test_published_event_reaches_a_live_consumer(self) -> None:
        sub = self.transport.subscribe()
        self.addCleanup(sub.close)
        time.sleep(0.2)  # let the ephemeral consumer attach
        self.transport.publish(_evt(1))
        self.assertEqual(sub.get(timeout=5), _evt(1))

    def test_multiple_consumers_each_receive(self) -> None:
        a = self.transport.subscribe()
        b = self.transport.subscribe()
        self.addCleanup(a.close)
        self.addCleanup(b.close)
        time.sleep(0.2)
        self.transport.publish(_evt(7))
        self.assertEqual(a.get(timeout=5), _evt(7))
        self.assertEqual(b.get(timeout=5), _evt(7))

    def test_buffer_wrapping_a_real_transport_passes_through(self) -> None:
        from recette.platform.realtime import BoundedRetryBuffer

        buf = BoundedRetryBuffer(self.transport)
        sub = self.transport.subscribe()
        self.addCleanup(sub.close)
        time.sleep(0.2)
        buf.publish(_evt(3))
        self.assertEqual(sub.get(timeout=5), _evt(3))
        self.assertFalse(buf.degraded)


if __name__ == "__main__":
    unittest.main()
