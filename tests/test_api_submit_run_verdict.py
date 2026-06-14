# tests/test_api_submit_run_verdict.py
"""POST /runs/{id}/submit-verdict: judge a real run and push it onto the
Verdicts board, exactly as an external identification tool would.

Closes the recette loop launch -> action log -> judged verdict -> /verdicts.
The submission is judged against the agent's stored ground_truth: a conform
run on an agent with ground truth is PASS; an agent without ground truth is
SKIP (never a vacuous PASS). Deterministic (judge_run is pure, I4)."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app
    from recette.api.config_store import ConfigStore
    from recette.api.verdict_store import VerdictStore

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover
    _HAS_FASTAPI = False

_STUB = [
    {"kind": "tool_call", "tool_name": "read_repo", "tool_args": {"resource": "acme/x"}},
    {"kind": "final", "text": "done"},
]


def _wait_terminal(client, run_id, tries=200):
    for _ in range(tries):
        s = client.get(f"/runs/{run_id}").json()["status"]
        if s in {"completed", "failed", "stopped"}:
            return s
        time.sleep(0.01)
    raise AssertionError("run did not terminate")


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class TestSubmitRunVerdict(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = store = ConfigStore(Path(self.tmp.name) / "cfg.json")
        # Conform agent WITH ground truth: a within-scope read_repo run must be
        # judged "correct" on all 4 dimensions and so PASS against this truth.
        store.add_agent(
            {
                "id": "gt-bot",
                "principal": "bot@acme",
                "target_system": "github",
                "goal": "read",
                "capability_scope": ["read_repo"],
                "ai_backend_id": "b1",
                "runtime": "lab",
                "ground_truth": {
                    "detectable": True,
                    "expected_identity": "bot@acme",
                    "expected_verdict": "correct",
                    "dimensions": {
                        "identity": True,
                        "capabilities": True,
                        "policy": True,
                        "behavior": True,
                    },
                },
            }
        )
        # Agent WITHOUT ground truth: a submission must be SKIP, not PASS.
        store.add_agent(
            {
                "id": "no-gt-bot",
                "principal": "p@acme",
                "target_system": "github",
                "goal": "read",
                "capability_scope": ["read_repo"],
                "ai_backend_id": "b1",
                "runtime": "lab",
            }
        )
        # Isolate the verdict board to a temp file so the test never writes the
        # runtime data/verdicts.json (R4: fixtures must not leak into runtime).
        self.client = TestClient(
            create_app(
                config_store=store,
                verdict_store=VerdictStore(Path(self.tmp.name) / "verdicts.json"),
            )
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _run(self, agent_id: str) -> str:
        r = self.client.post(
            "/runs",
            json={"kind": "lane_b", "params": {"agent_id": agent_id, "stub_script": _STUB}},
        )
        self.assertEqual(r.status_code, 201)
        run_id = r.json()["run_id"]
        self.assertEqual(_wait_terminal(self.client, run_id), "completed")
        return run_id

    def test_conform_run_submits_pass_and_shows_on_board(self) -> None:
        run_id = self._run("gt-bot")
        r = self.client.post(f"/runs/{run_id}/submit-verdict")
        self.assertEqual(r.status_code, 201)
        body = r.json()
        self.assertEqual(body["agent_id"], "gt-bot")
        self.assertEqual(len(body["judged"]), 1)
        self.assertEqual(body["judged"][0]["status"], "PASS")
        # The board (GET /verdicts) now shows this submission as the latest.
        latest = self.client.get("/verdicts").json()
        self.assertEqual(latest["tool"], f"run:{run_id}")
        self.assertEqual(latest["judged"][0]["agent_id"], "gt-bot")
        self.assertEqual(latest["judged"][0]["status"], "PASS")
        # And the scorecard counts it as a passed detection.
        card = self.client.get("/verdicts/scorecard").json()
        self.assertEqual(card["total"], 1)
        self.assertEqual(card["passed"], 1)
        self.assertEqual(card["detection_rate"], 1.0)

    def test_agent_without_ground_truth_is_skip(self) -> None:
        run_id = self._run("no-gt-bot")
        body = self.client.post(f"/runs/{run_id}/submit-verdict").json()
        self.assertEqual(body["judged"][0]["status"], "SKIP")

    def test_deterministic_resubmission(self) -> None:
        """Same run submitted twice yields a byte-identical judged entry (I4)."""
        run_id = self._run("gt-bot")
        a = self.client.post(f"/runs/{run_id}/submit-verdict").json()["judged"][0]
        b = self.client.post(f"/runs/{run_id}/submit-verdict").json()["judged"][0]
        self.assertEqual(a, b)

    def test_unknown_run_404(self) -> None:
        self.assertEqual(self.client.post("/runs/deadbeef/submit-verdict").status_code, 404)


if __name__ == "__main__":
    unittest.main()
