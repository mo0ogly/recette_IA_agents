"""Dry-run endpoint: executes a mock scenario in-memory, persists nothing (I1),
mock-only, deterministic (I4)."""

from __future__ import annotations

import unittest

from recette.api.runners import dry_run_lane_b

_AGENT = {
    "id": "dry-bot",
    "principal": "bot@acme",
    "target_system": "github",
    "goal": "read then open",
    "capability_scope": ["read_repo", "open_pr"],
    "ai_mode": "mock",
    "scenario": [
        {"kind": "tool_call", "tool_name": "read_repo", "tool_args": {"resource": "acme/x"}},
        {"kind": "tool_call", "tool_name": "open_pr", "tool_args": {"resource": "acme/x"}},
        {"kind": "final", "text": "done"},
    ],
}


class TestDryRunFunction(unittest.TestCase):
    def test_runs_scenario_and_returns_action_log(self) -> None:
        out = dry_run_lane_b(_AGENT)
        self.assertEqual([a["action_type"] for a in out["actions"]], ["read_repo", "open_pr"])
        self.assertEqual(len(out["steps"]), 3)  # 2 tool calls + final

    def test_is_deterministic(self) -> None:
        self.assertEqual(dry_run_lane_b(_AGENT), dry_run_lane_b(_AGENT))

    def test_real_ai_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            dry_run_lane_b({**_AGENT, "ai_mode": "real"})

    def test_missing_fields_rejected(self) -> None:
        with self.assertRaises(ValueError):
            dry_run_lane_b({"id": "x", "ai_mode": "mock", "scenario": _AGENT["scenario"]})

    def test_no_scenario_rejected(self) -> None:
        with self.assertRaises(ValueError):
            dry_run_lane_b({**_AGENT, "scenario": []})


try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app

    _HAVE_FASTAPI = True
except ImportError:  # pragma: no cover
    _HAVE_FASTAPI = False


@unittest.skipUnless(_HAVE_FASTAPI, "fastapi not installed")
class TestDryRunRoute(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_post_dry_run_ok(self) -> None:
        r = self.client.post("/runs/dry-run", json=_AGENT)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()["actions"]), 2)

    def test_post_dry_run_real_is_400(self) -> None:
        r = self.client.post("/runs/dry-run", json={**_AGENT, "ai_mode": "real"})
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
