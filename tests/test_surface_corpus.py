"""The surface corpus subjects: the reference adapter must reproduce each
subject's ground-truth per-surface detection exactly (self-consistency)."""

from __future__ import annotations

import unittest

from recette.surface.corpus import load_surface_subjects
from recette.surface.detect import ReferenceSurfaceDiscoveryAdapter, detect_agent


class TestSurfaceCorpus(unittest.TestCase):
    def test_subjects_load(self) -> None:
        # The thesis corpus broadened (#9): the two originals plus a ghost
        # exfiltrating to the honeypot sink and a hook-only (wire-invisible) agent.
        subjects = load_surface_subjects()
        ids = sorted(s["agent_id"] for s in subjects)
        self.assertEqual(ids, ["exfil-to-sink", "ghost-direct-db", "hook-only-mock", "pr-bot-sdk"])

    def test_reference_adapter_matches_each_ground_truth(self) -> None:
        for subject in load_surface_subjects():
            result = detect_agent(
                agent_id=subject["agent_id"],
                proxy_traces=subject["run"]["proxy_traces"],
                wire_flows=subject["run"]["wire_flows"],
                adapter=ReferenceSurfaceDiscoveryAdapter(),
            )
            expected = subject["ground_truth"]["expected"]
            self.assertEqual(
                result.detected_anywhere,
                expected["detected_anywhere"],
                f"{subject['agent_id']}: detected_anywhere mismatch",
            )
            by_surface = {d.surface.value: d.detected for d in result.per_surface}
            for surface, want in expected["per_surface"].items():
                self.assertEqual(by_surface[surface], want, f"{subject['agent_id']}:{surface}")

    def test_ghost_is_a_hook_blind_spot(self) -> None:
        ghost = next(s for s in load_surface_subjects() if s["agent_id"] == "ghost-direct-db")
        exp = ghost["ground_truth"]["expected"]["per_surface"]
        self.assertFalse(exp["hook_sdk"])
        self.assertTrue(exp["ebpf_wire"])


if __name__ == "__main__":
    unittest.main()
