"""Tests for recette/runs/capture.py (Task 6).

Run:  python3 -m unittest tests.test_runs_capture -v
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from recette.runs.capture import capture_surface
from recette.runs.registry import RunRegistry


class TestCaptureSurface(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.reg = RunRegistry(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_capture_surface_seals_group_with_two_runs(self) -> None:
        reg = capture_surface(
            category="recette-full",
            group_id="test-batch-1",
            eurodate="2026-06-25T10-00-00",
            label="test run",
            runs={
                "sweep-results": {
                    "kind": "recette-full",
                    "artifacts": {
                        "results.json": '{"passed":true}',
                        "retex.md": "# RETEX\nAll pass.",
                    },
                },
                "scorecard": {
                    "kind": "recette-full",
                    "artifacts": {
                        "scorecard.json": '{"score":95}',
                    },
                },
            },
            registry=self.reg,
        )
        self.assertIsNotNone(reg)

        # Both runs are readable via tree().
        tree = self.reg.tree()
        cats = {c["category"] for c in tree["categories"]}
        self.assertIn("recette-full", cats)
        cat = next(c for c in tree["categories"] if c["category"] == "recette-full")
        all_run_ids = [r["id"] for g in cat["groups"] for r in g["runs"]]
        self.assertIn("sweep-results", all_run_ids)
        self.assertIn("scorecard", all_run_ids)

    def test_capture_surface_seals_runs(self) -> None:
        capture_surface(
            category="agents",
            group_id="fleet-1",
            eurodate="2026-06-25T11-00-00",
            label="fleet",
            runs={
                "agent-a": {
                    "kind": "agent",
                    "artifacts": {"log.jsonl": '{"ok":true}\n'},
                }
            },
            registry=self.reg,
        )
        doc = self.reg.read_run("agent-a")
        self.assertEqual(doc["meta"]["status"], "sealed")
        self.assertIn("log.jsonl", doc["artifacts"])

    def test_capture_surface_is_hash_stable(self) -> None:
        """Same inputs on two separate registries produce the same root_hash."""
        reg2_root = Path(self._tmp.name) / "reg2"
        reg2 = RunRegistry(reg2_root)

        common_runs: dict[str, dict[str, Any]] = {
            "run-x": {
                "kind": "campaign",
                "artifacts": {"out.jsonl": '{"result":"pass"}\n'},
            }
        }

        capture_surface(
            category="campaigns",
            group_id="batch",
            eurodate="2026-06-25T12-00-00",
            label="batch run",
            runs=common_runs,
            registry=self.reg,
        )
        capture_surface(
            category="campaigns",
            group_id="batch",
            eurodate="2026-06-25T12-00-00",
            label="batch run",
            runs=common_runs,
            registry=reg2,
        )

        hash1 = self.reg.read_run("run-x")["meta"]["root_hash"]
        hash2 = reg2.read_run("run-x")["meta"]["root_hash"]
        self.assertEqual(hash1, hash2)

    def test_capture_surface_failure_is_non_fatal(self) -> None:
        """A bad artifact name must not raise -- returns None."""
        # Inject a bad artifact name to trigger ValueError inside capture.
        result = capture_surface(
            category="agents",
            group_id="bad",
            eurodate="2026-06-25T13-00-00",
            label="bad",
            runs={
                "run-bad": {
                    "kind": "agent",
                    "artifacts": {"../escape.txt": "oops"},
                }
            },
            registry=self.reg,
        )
        # Capture failed -> returns None (fail-safe, no exception propagated).
        self.assertIsNone(result)

    def test_capture_surface_empty_runs(self) -> None:
        """Empty runs dict creates an empty sealed group."""
        reg = capture_surface(
            category="discovery",
            group_id="empty-batch",
            eurodate="2026-06-25T14-00-00",
            label="empty",
            runs={},
            registry=self.reg,
        )
        self.assertIsNotNone(reg)
        # Group dir exists.
        tree = self.reg.tree()
        cats = {c["category"] for c in tree["categories"]}
        self.assertIn("discovery", cats)


if __name__ == "__main__":
    unittest.main()
