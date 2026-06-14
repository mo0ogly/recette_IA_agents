"""Unit tests for the DiscoveryScorecard data model."""

from __future__ import annotations

import unittest

from recette.discovery_scorecard import DiscoveryRepoResult, DiscoveryScorecard


def _res(repo, matches, **kw):
    return DiscoveryRepoResult(
        repo=repo,
        detected_expected=kw.get("detected_expected", True),
        detected_actual=kw.get("detected_actual", True),
        matches=matches,
        false_positive=kw.get("false_positive", False),
        false_negative=kw.get("false_negative", False),
    )


class TestDiscoveryScorecard(unittest.TestCase):
    def test_empty(self):
        sc = DiscoveryScorecard()
        self.assertEqual(sc.total, 0)
        self.assertFalse(sc.all_passed)
        self.assertEqual(sc.detection_rate, 0.0)

    def test_all_pass(self):
        sc = DiscoveryScorecard()
        sc.add(_res("a", {"detection": True, "actions": True, "determinism": True}))
        sc.add(_res("b", {"detection": True, "determinism": True}))
        self.assertTrue(sc.all_passed)
        self.assertEqual(sc.detection_rate, 1.0)

    def test_dimension_accuracy_only_over_applicable(self):
        sc = DiscoveryScorecard()
        sc.add(_res("a", {"detection": True, "actions": True}))
        sc.add(_res("b", {"detection": True}))  # no 'actions' dim
        self.assertEqual(sc.dimension_accuracy("actions"), 1.0)  # 1/1 applicable

    def test_broken_ordering_fails_all(self):
        sc = DiscoveryScorecard()
        sc.add(_res("a", {"detection": True}))
        sc.ordering_ok = False
        sc.ordering_detail = "x outranks y"
        self.assertFalse(sc.all_passed)

    def test_false_negative_tally(self):
        sc = DiscoveryScorecard()
        sc.add(_res("a", {"detection": False}, false_negative=True, detected_actual=False))
        self.assertEqual(sc.false_negatives, 1)
        self.assertFalse(sc.all_passed)


if __name__ == "__main__":
    unittest.main()
