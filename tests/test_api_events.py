"""G4 realtime stream API: governed appends are diffused to a live subscriber,
and GET /events/status reports transport health.

The diffusion is asserted at the transport seam (an InProcessTransport injected
into create_app and subscribed directly) rather than over a live SSE socket, so
the test is deterministic and free of timing flakiness. The end-to-end SSE socket
is covered by the console browser smoke (R16)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover - exercised only without the [api] extra
    _HAS_FASTAPI = False

from recette.api.config_store import ConfigStore
from recette.platform.catalog import Catalog
from recette.platform.eventstore.memory_store import InMemoryEventStore
from recette.platform.policy.store import PolicyStore
from recette.platform.realtime import InProcessTransport
from tests.test_api_platform import SPECS, StubProxy


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class TestEventsStreamApi(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tmp = Path(self._tmp.name)
        self.transport = InProcessTransport()
        self.addCleanup(self.transport.close)
        self.app = create_app(
            config_store=ConfigStore(tmp / "config.json"),
            event_store=InMemoryEventStore(),
            policy_store=PolicyStore(tmp / "policies"),
            proxy=StubProxy(),
            catalog=Catalog(SPECS),
            realtime_transport=self.transport,
        )
        self.client = TestClient(self.app)
        resp = self.client.post(
            "/config/agents",
            json={
                "id": "agent-admin",
                "runtime": "lab",
                "role": "identity_admin",
                "capability_scope": ["okta"],
            },
        )
        self.assertEqual(resp.status_code, 201, resp.text)

    def test_executed_action_is_diffused_to_a_live_subscriber(self) -> None:
        sub = self.transport.subscribe()
        self.addCleanup(sub.close)
        resp = self.client.post(
            "/actions/execute",
            json={
                "agent_id": "agent-admin",
                "action_type": "list_users",
                "target_system": "okta",
                "resource": "org/acme",
                "payload": {"reason": "test"},
            },
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        event_id = resp.json()["event_id"]
        # The append went to the store (truth) AND fanned out to the live stream.
        diffused = sub.get(timeout=2)
        self.assertIsNotNone(diffused)
        self.assertEqual(diffused["event_id"], event_id)
        self.assertEqual(diffused["kind"], "action_executed")

    def test_denied_action_is_also_diffused(self) -> None:
        self.client.post(
            "/config/agents",
            json={
                "id": "agent-bot",
                "runtime": "lab",
                "role": "marketing_bot",
                "capability_scope": [],
            },
        )
        sub = self.transport.subscribe()
        self.addCleanup(sub.close)
        self.client.post(
            "/actions/execute",
            json={
                "agent_id": "agent-bot",
                "action_type": "suspend_user",
                "target_system": "okta",
                "resource": "org/acme",
                "payload": {},
            },
        )
        diffused = sub.get(timeout=2)
        self.assertIsNotNone(diffused)
        self.assertEqual(diffused["kind"], "action_denied")

    def test_status_endpoint_reports_healthy_inproc(self) -> None:
        body = self.client.get("/events/status").json()
        self.assertEqual(body, {"degraded": False, "pending": 0, "dropped": 0})


if __name__ == "__main__":
    unittest.main()
