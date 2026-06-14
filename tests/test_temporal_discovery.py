"""Tests for the Temporal discovery surface: oracle reproduces ground-truth + harness PASS.

The corpus is real temporalio code; the oracle parses it statically (AST), so these
tests need no temporalio install. Asserts invariant properties only.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from recette.adapters import ReferenceSourceScanAdapter
from recette.discovery_harness import SURFACE_CORPUS, run_discovery_recette

REPO = Path(__file__).resolve().parent.parent
TEMPORAL = SURFACE_CORPUS["temporal"]

DETECTED = ["tmpl-readonly-reporter", "tmpl-pr-bot", "tmpl-admin-overreach"]
ALL = [*DETECTED, "tmpl-no-agent"]


def _gt(slug: str) -> dict:
    return json.loads((TEMPORAL / slug / "discovery-ground-truth.json").read_text(encoding="utf-8"))


def _scan(slug: str):
    a = ReferenceSourceScanAdapter()
    sid = a.register(str(TEMPORAL / slug / "repo"))
    a.await_run(a.scan(sid))
    return a.risks(sid)


class TestTemporalReferenceScan(unittest.TestCase):
    def test_detection_matches_ground_truth(self):
        for slug in ALL:
            with self.subTest(slug=slug):
                self.assertEqual(len(_scan(slug)) > 0, _gt(slug)["detected"])

    def test_action_pattern_coverage(self):
        for slug in DETECTED:
            with self.subTest(slug=slug):
                got = {r.action_pattern for r in _scan(slug)}
                self.assertEqual(got, set(_gt(slug)["action_patterns"]))

    def test_target_system_is_temporal(self):
        for slug in DETECTED:
            with self.subTest(slug=slug):
                self.assertTrue(all(r.target_system == "temporal" for r in _scan(slug)))

    def test_policy_presence_matches_ground_truth(self):
        for slug in DETECTED:
            with self.subTest(slug=slug):
                present = any(bool(r.generated_policy) for r in _scan(slug))
                self.assertEqual(present, _gt(slug)["policy_generated"])

    def test_no_agent_is_true_negative(self):
        # A plain temporalio workflow with no canonical-action activity must not be flagged.
        self.assertEqual(_scan("tmpl-no-agent"), [])

    def test_single_agent_per_subject(self):
        for slug in DETECTED:
            with self.subTest(slug=slug):
                ids = {r.canonical_agent_id for r in _scan(slug)}
                self.assertEqual(len(ids), 1)

    def test_scan_is_deterministic(self):
        for slug in ALL:
            with self.subTest(slug=slug):
                first = _scan(slug)
                second = _scan(slug)
                self.assertEqual(
                    [(r.canonical_agent_id, r.action_pattern, r.estimated_risk) for r in first],
                    [(r.canonical_agent_id, r.action_pattern, r.estimated_risk) for r in second],
                )


class TestTemporalHarness(unittest.TestCase):
    def test_full_temporal_recette_passes(self):
        scorecard = run_discovery_recette(corpus_root=TEMPORAL)
        self.assertTrue(scorecard.all_passed, "\n" + scorecard.render())
        self.assertEqual(scorecard.false_positives, 0)
        self.assertEqual(scorecard.false_negatives, 0)
        self.assertTrue(scorecard.ordering_ok)


if __name__ == "__main__":
    unittest.main()
