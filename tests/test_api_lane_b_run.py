# tests/test_api_lane_b_run.py
"""U1: a registered Lane B agent runs via the API and streams step frames (stubbed LLM)."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app
    from recette.api.config_store import ConfigStore

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover
    _HAS_FASTAPI = False


def _wait_terminal(client, run_id, tries=200):
    for _ in range(tries):
        s = client.get(f"/runs/{run_id}").json()["status"]
        if s in {"completed", "failed", "stopped"}:
            return s
        time.sleep(0.01)
    raise AssertionError("no terminate")


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class TestLaneBRun(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        store = ConfigStore(Path(self.tmp.name) / "cfg.json")
        store.add_agent(
            {
                "id": "a1",
                "principal": "acme-bot@github",
                "target_system": "github",
                "goal": "bump deps",
                "capability_scope": ["read_repo", "open_pr"],
                "ai_backend_id": "b1",
                "runtime": "lab",
            }
        )
        self.client = TestClient(create_app(config_store=store))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_lane_b_run_streams_steps(self) -> None:
        stub = [
            {"kind": "tool_call", "tool_name": "read_repo", "tool_args": {"resource": "acme/x"}},
            {"kind": "final", "text": "done"},
        ]
        r = self.client.post(
            "/runs", json={"kind": "lane_b", "params": {"agent_id": "a1", "stub_script": stub}}
        )
        self.assertEqual(r.status_code, 201)
        run_id = r.json()["run_id"]
        self.assertEqual(_wait_terminal(self.client, run_id), "completed")
        events = self.client.get(f"/runs/{run_id}/events").json()
        self.assertTrue(any(e["type"] == "step" for e in events))
        self.assertTrue(any(e["type"] == "result" for e in events))

    def test_register_agent_then_in_catalog(self) -> None:
        r = self.client.post(
            "/agents/register",
            json={
                "id": "a2",
                "principal": "p",
                "target_system": "github",
                "goal": "g",
                "capability_scope": ["read_repo"],
                "ai_backend_id": "b1",
                "runtime": "lab",
            },
        )
        self.assertEqual(r.status_code, 201)
        lane_b_ids = {a["id"] for a in self.client.get("/agents").json()["lane_b"]}
        self.assertIn("a2", lane_b_ids)
