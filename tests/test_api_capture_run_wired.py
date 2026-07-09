# tests/test_api_capture_run_wired.py
"""T1: a lane_b run wires the capture sink -> GET /capture/llm-traces is populated.

Regression guard for the disconnected-capture bug: make_lane_b_runner accepts a
``capture_sink`` but the /runs launch never passed it, so the per-run capture
ring (and thus GET /capture/llm-traces, the console LlmTracePanel) stayed empty.
This asserts a stub run now records its LLM decisions into that ring, and that an
unknown run stays empty (fail-safe, no cross-run leak)."""

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
class TestCaptureRunWired(unittest.TestCase):
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

    def test_run_populates_capture_llm_traces(self) -> None:
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

        # T1: the capture sink was wired -> the run's LLM decisions are recorded
        # and readable through the same endpoint the console LlmTracePanel uses.
        cap = self.client.get(f"/capture/llm-traces?run_id={run_id}").json()
        self.assertEqual(cap["run_id"], run_id)
        self.assertGreaterEqual(cap["count"], 1)
        self.assertEqual(len(cap["traces"]), cap["count"])

        # Fail-safe: an unknown run stays empty (no cross-run leak).
        empty = self.client.get("/capture/llm-traces?run_id=does-not-exist").json()
        self.assertEqual(empty["count"], 0)
