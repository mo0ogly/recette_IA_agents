"""M8 coverage audit for the discovery corpus: every surface is complete and well-formed.

Each surface must carry exactly one true-negative (the false-positive guard) and at least
one detected subject, each with a positive risk rank. Rank TIES are allowed by design
(mono-axis subjects can share a rank); the corpus invariant enforces only monotonicity.
This is the discovery counterpart to the identification orthogonality audit in test_recette.py.
"""

from __future__ import annotations

import json
import unittest

from recette.discovery_harness import SURFACE_CORPUS, SURFACE_ORDER, discover_repo_dirs


def _surfaces_with_corpus() -> list[str]:
    return [s for s in SURFACE_ORDER if discover_repo_dirs(SURFACE_CORPUS[s])]


def _ground_truths(surface: str) -> list[dict]:
    return [
        json.loads((d / "discovery-ground-truth.json").read_text(encoding="utf-8"))
        for d in discover_repo_dirs(SURFACE_CORPUS[surface])
    ]


class TestDiscoveryCoverage(unittest.TestCase):
    def test_there_is_at_least_one_corpus_surface(self):
        self.assertTrue(_surfaces_with_corpus())

    def test_each_surface_has_exactly_one_true_negative(self):
        for surface in _surfaces_with_corpus():
            with self.subTest(surface=surface):
                negatives = [gt for gt in _ground_truths(surface) if not gt["detected"]]
                self.assertEqual(len(negatives), 1, f"{surface}: need exactly one true-negative")

    def test_each_surface_has_detected_subjects(self):
        for surface in _surfaces_with_corpus():
            with self.subTest(surface=surface):
                detected = [gt for gt in _ground_truths(surface) if gt["detected"]]
                self.assertGreaterEqual(len(detected), 1)

    def test_detected_ranks_are_positive(self):
        # Every detected subject carries a positive risk_rank (>= 1). Rank TIES are
        # allowed by design: the real corpus invariant (discovery_harness._check_ordering)
        # only enforces MONOTONICITY -- it fires when ranks[a] < ranks[b] yet the risk
        # LEVELS invert, never on equal ranks. Mono-axis subjects (gh-shadow-agent,
        # gh-invalid-passport) deliberately share rank 2 with gh-pr-bot: passport_status
        # is the only differing axis, so their risk_rank must stay equal.
        for surface in _surfaces_with_corpus():
            with self.subTest(surface=surface):
                ranks = [gt["risk_rank"] for gt in _ground_truths(surface) if gt["detected"]]
                self.assertTrue(ranks, f"{surface}: expected at least one detected rank")
                self.assertTrue(all(r >= 1 for r in ranks), f"{surface}: rank must be >= 1")

    def test_true_negative_is_well_formed(self):
        for surface in _surfaces_with_corpus():
            with self.subTest(surface=surface):
                tn = next(gt for gt in _ground_truths(surface) if not gt["detected"])
                self.assertEqual(tn["risk_rank"], 0)
                self.assertEqual(tn.get("agent_count", 0), 0)
                self.assertEqual(tn.get("action_patterns", []), [])
                self.assertFalse(tn.get("policy_generated", False))


if __name__ == "__main__":
    unittest.main()
