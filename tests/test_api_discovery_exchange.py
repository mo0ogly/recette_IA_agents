"""Endpoint test for GET /proxy/discovery-exchange (discovery verdict overlay).

Container-free: seed the wire recorder via POST /proxy/wire, then assert the
endpoint returns the overlay envelope and that a wire flow to a non-mediated
target is reported as a ghost exchange. Hook traces are produced by a real run
(covered by the pure composer test); here we prove the route wiring + the
wire/ghost half + a stable empty report.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app
    from recette.api.config_store import ConfigStore
    from recette.platform.eventstore.memory_store import InMemoryEventStore

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover - depends on the [api] extra
    _HAS_FASTAPI = False


def _flow(**over: object) -> dict:
    base = {
        "method": "POST",
        "scheme": "http",
        "host": "127.0.0.1",
        "port": 8082,
        "path": "/github/execute",
        "status_code": 200,
        "request_body": "{}",
        "response_body": "{}",
        "run_id": "run-1",
    }
    base.update(over)
    return base


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class DiscoveryExchangeEndpointTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        cfg_path = Path(self._tmpdir.name) / "config.json"
        self.client = TestClient(
            create_app(
                event_store=InMemoryEventStore(),
                config_store=ConfigStore(cfg_path),
                # Explicit :memory: proxy store: under `unittest discover -s
                # tests` modules import top-level, so the tests/__init__.py
                # env pin never runs and bare create_app() would share the
                # persistent .run/proxy_traces.db -- wire flows posted by one
                # test would leak into the next (order-dependent failures).
                proxy_db_path=":memory:",
            )
        )

    def test_empty_buffers_yield_a_stable_empty_overlay(self) -> None:
        body = self.client.get("/proxy/discovery-exchange").json()
        self.assertIn("debug_enabled", body)
        self.assertEqual(body["agents"], [])
        self.assertEqual(body["exchanges"], [])
        self.assertEqual(body["ghost_exchanges"], 0)
        self.assertTrue(body["scorecard"]["ok"])

    def test_wire_only_flow_to_non_mediated_target_is_a_ghost_exchange(self) -> None:
        self.client.post("/proxy/wire", json=_flow(host="evil.test", port=443, path="/leak"))
        body = self.client.get("/proxy/discovery-exchange", params={"run_id": "run-1"}).json()
        self.assertEqual(body["ghost_exchanges"], 1)
        wire = [e for e in body["exchanges"] if e["kind"] == "wire"]
        self.assertEqual(len(wire), 1)
        self.assertFalse(wire[0]["identified"])
        self.assertEqual(wire[0]["reason"], "non_mediated_target")

    def test_mediated_flow_is_not_a_ghost_exchange(self) -> None:
        # A benign flow to the lab (allowlisted, non-/execute) is explained.
        self.client.post("/proxy/wire", json=_flow(port=8082, path="/health"))
        body = self.client.get("/proxy/discovery-exchange", params={"run_id": "run-1"}).json()
        self.assertEqual(body["ghost_exchanges"], 0)


if __name__ == "__main__":
    unittest.main()
