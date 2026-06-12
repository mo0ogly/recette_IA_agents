"""U1: RunManager core (threaded run, event frames, stop) — no event loop here."""

from __future__ import annotations

import unittest

from recette.api.runners import identification_runner
from recette.api.runs import RunManager


class TestRunManager(unittest.TestCase):
    def setUp(self) -> None:
        self.mgr = RunManager()

    def test_identification_run_completes_with_scorecard(self) -> None:
        run = self.mgr.create("identification", {})
        self.mgr.run_blocking(run, identification_runner)  # test helper: run inline, no thread
        self.assertEqual(run.status, "completed")
        types = [e["type"] for e in run.events]
        self.assertEqual(types[0], "start")
        self.assertIn("agent_result", types)
        self.assertEqual(types[-1], "end")
        scorecard = next(e for e in run.events if e["type"] == "scorecard")
        self.assertIn("passed", scorecard["data"])
        self.assertIn("total", scorecard["data"])

    def test_event_seq_is_monotonic(self) -> None:
        run = self.mgr.create("identification", {})
        self.mgr.run_blocking(run, identification_runner)
        seqs = [e["seq"] for e in run.events]
        self.assertEqual(seqs, sorted(seqs))
        self.assertEqual(len(seqs), len(set(seqs)))

    def test_stop_flag_halts_identification(self) -> None:
        run = self.mgr.create("identification", {})
        self.mgr.request_stop(run.id)  # stop before it starts
        self.mgr.run_blocking(run, identification_runner)
        self.assertEqual(run.status, "stopped")
