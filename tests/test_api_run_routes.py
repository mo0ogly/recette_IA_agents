# tests/test_api_run_routes.py
"""U1: launch/inspect/stop runs over HTTP."""

from __future__ import annotations

import time
import unittest

try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover
    _HAS_FASTAPI = False


def _wait_terminal(client, run_id, tries=200):
    for _ in range(tries):
        body = client.get(f"/runs/{run_id}").json()
        if body["status"] in {"completed", "failed", "stopped"}:
            return body
        time.sleep(0.01)
    raise AssertionError("run did not terminate")


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class TestRunRoutes(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_launch_identification_then_scorecard(self) -> None:
        r = self.client.post("/runs", json={"kind": "identification", "params": {}})
        self.assertEqual(r.status_code, 201)
        run_id = r.json()["run_id"]
        body = _wait_terminal(self.client, run_id)
        self.assertEqual(body["status"], "completed")
        events = self.client.get(f"/runs/{run_id}/events").json()
        self.assertTrue(any(e["type"] == "scorecard" for e in events))

    def test_unknown_kind_400(self) -> None:
        self.assertEqual(
            self.client.post("/runs", json={"kind": "nope", "params": {}}).status_code, 400
        )

    def test_get_unknown_run_404(self) -> None:
        self.assertEqual(self.client.get("/runs/deadbeef").status_code, 404)

    def test_stop_unknown_run_404(self) -> None:
        self.assertEqual(self.client.post("/runs/deadbeef/stop").status_code, 404)
