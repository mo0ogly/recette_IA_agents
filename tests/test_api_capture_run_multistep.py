# tests/test_api_capture_run_multistep.py
"""T3: a multi-step agent produces a long, readable LLM-trace exchange.

The mock loop stops early on a repeated (tool_name, resource) signature
(lane_b.py stop_on_repeat) and at the first ``final``, so a study-grade long
exchange needs DISTINCT actions each step. This runs an 8-decision agent
(7 distinct tool calls then a final) and asserts every decision surfaced through
GET /capture/llm-traces -- the material a researcher studies step by step. It is
the observable proof that, wiring aside (T1), a run CAN carry a long exchange."""

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

# A realistic multi-step maintenance agent: read several repo resources, open a
# PR, re-read, then conclude. Distinct (tool, resource) each step so neither
# stop_on_repeat nor the first-final cut the exchange short.
MULTISTEP_SCRIPT = [
    {"kind": "tool_call", "tool_name": "read_repo", "tool_args": {"resource": "acme/app@manifest"}},
    {"kind": "tool_call", "tool_name": "read_repo", "tool_args": {"resource": "acme/app@lockfile"}},
    {"kind": "tool_call", "tool_name": "read_repo", "tool_args": {"resource": "acme/app@changelog"}},
    {"kind": "tool_call", "tool_name": "read_repo", "tool_args": {"resource": "acme/app@ci-config"}},
    {"kind": "tool_call", "tool_name": "read_repo", "tool_args": {"resource": "acme/app@readme"}},
    {"kind": "tool_call", "tool_name": "open_pr", "tool_args": {"resource": "acme/app#bump-deps"}},
    {"kind": "tool_call", "tool_name": "read_repo", "tool_args": {"resource": "acme/app@review"}},
    {"kind": "final", "text": "Opened the dependency-bump PR after reviewing the repo."},
]


def _wait_terminal(client, run_id, tries=300):
    for _ in range(tries):
        s = client.get(f"/runs/{run_id}").json()["status"]
        if s in {"completed", "failed", "stopped"}:
            return s
        time.sleep(0.01)
    raise AssertionError("no terminate")


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class TestCaptureRunMultistep(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        store = ConfigStore(Path(self.tmp.name) / "cfg.json")
        store.add_agent(
            {
                "id": "maintainer",
                "principal": "acme-bot@github",
                "target_system": "github",
                "goal": "bump dependencies after reviewing the repo",
                "capability_scope": ["read_repo", "open_pr"],
                "ai_backend_id": "b1",
                "runtime": "lab",
            }
        )
        self.client = TestClient(create_app(config_store=store))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_multistep_run_surfaces_a_long_llm_trace(self) -> None:
        r = self.client.post(
            "/runs",
            json={
                "kind": "lane_b",
                "params": {"agent_id": "maintainer", "stub_script": MULTISTEP_SCRIPT},
            },
        )
        self.assertEqual(r.status_code, 201)
        run_id = r.json()["run_id"]
        self.assertEqual(_wait_terminal(self.client, run_id), "completed")

        cap = self.client.get(f"/capture/llm-traces?run_id={run_id}").json()
        # A long exchange: at least the 7 tool decisions surfaced (the final may
        # or may not be captured depending on the loop's last decide()).
        self.assertGreaterEqual(cap["count"], 7)
        traces = cap["traces"]
        # It is genuinely multi-step: several distinct resources were reasoned
        # over (not one repeated action collapsed by stop_on_repeat).
        resources = {t.get("resource") for t in traces}
        self.assertGreaterEqual(len(resources), 6)
        # Both tools the agent used show up in the captured decisions.
        tools = {t.get("tool_name") for t in traces}
        self.assertIn("read_repo", tools)
        self.assertIn("open_pr", tools)
