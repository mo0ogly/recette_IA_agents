"""The surface NEGATIVE corpus: a subject seen on no surface must turn the
scorecard RED. Lives under corpus/surface/_negative/ so the green `recette
surface` run (which scores only the real subjects) never includes it."""

from __future__ import annotations

import unittest

from recette.surface.corpus import load_surface_negatives, load_surface_subjects
from recette.surface.detect import ReferenceSurfaceDiscoveryAdapter, detect_agent
from recette.surface.scorecard import score_detections


class TestSurfaceNegative(unittest.TestCase):
    def test_negatives_are_excluded_from_the_green_subjects(self) -> None:
        # The green-scoring loader must skip the _negative directory.
        ids = sorted(s["agent_id"] for s in load_surface_subjects())
        self.assertNotIn("vanished", ids)
        self.assertEqual(ids, ["exfil-to-sink", "ghost-direct-db", "hook-only-mock", "pr-bot-sdk"])

    def test_vanished_subject_loads_from_the_negative_corpus(self) -> None:
        negatives = load_surface_negatives()
        ids = sorted(s["agent_id"] for s in negatives)
        self.assertEqual(ids, ["vanished"])

    def test_vanished_turns_the_scorecard_red(self) -> None:
        vanished = load_surface_negatives()[0]
        result = detect_agent(
            agent_id=vanished["agent_id"],
            proxy_traces=vanished["run"]["proxy_traces"],
            wire_flows=vanished["run"]["wire_flows"],
            adapter=ReferenceSurfaceDiscoveryAdapter(),
        )
        # Reference adapter reproduces the ground-truth: seen nowhere.
        self.assertFalse(result.detected_anywhere)
        self.assertEqual(
            result.detected_anywhere,
            vanished["ground_truth"]["expected"]["detected_anywhere"],
        )
        card = score_detections([result])
        self.assertFalse(card.ok)  # the red gate fires
        self.assertEqual(card.false_negatives, ("vanished",))


if __name__ == "__main__":
    unittest.main()
