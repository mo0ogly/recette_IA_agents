"""Frozen red-team / simulation runs: persistence + step-through view (I1/I4)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from recette.sim_view import SimRecording, build_sim_view

_SIM_DIR = Path(__file__).resolve().parents[1] / "corpus" / "sim"


class TestCommittedSimCorpus(unittest.TestCase):
    def test_corpus_present(self) -> None:
        self.assertTrue(list(_SIM_DIR.glob("*.sim.json")))

    def test_clean_run_view(self) -> None:
        view = build_sim_view(SimRecording.load(_SIM_DIR / "sim-diagnostic-clean.sim.json"))
        self.assertEqual(view["verdict"], "correct")
        self.assertEqual(view["stopped_reason"], "completed")
        self.assertTrue(view["turns"])
        self.assertEqual(view["checks"], [])

    def test_redteam_run_view_flags_overreach(self) -> None:
        view = build_sim_view(SimRecording.load(_SIM_DIR / "sim-diagnostic-redteam.sim.json"))
        self.assertEqual(view["verdict"], "incorrect")
        self.assertFalse(view["dimensions"]["capabilities"])
        self.assertEqual(view["stopped_reason"], "check_failed")
        self.assertFalse(view["checks"][0]["passed"])

    def test_view_is_deterministic(self) -> None:
        rec = SimRecording.load(_SIM_DIR / "sim-diagnostic-clean.sim.json")
        self.assertEqual(build_sim_view(rec), build_sim_view(rec))


class TestRoundTrip(unittest.TestCase):
    def test_recording_round_trips_through_disk(self) -> None:
        rec = SimRecording.load(_SIM_DIR / "sim-diagnostic-redteam.sim.json")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.sim.json"
            rec.save(path)
            loaded = SimRecording.load(path)
        self.assertEqual(build_sim_view(loaded)["verdict"], "incorrect")


if __name__ == "__main__":
    unittest.main()
