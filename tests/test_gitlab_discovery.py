"""Tests for GitLab discovery parity: oracle reproduces ground-truth + harness PASS.

Manifest-driven (target_system=gitlab); the oracle resolves it via the shared manifest
precedence. Asserts invariant properties only.
"""

from __future__ import annotations

import json
import unittest

from recette.adapters import ReferenceSourceScanAdapter
from recette.discovery_harness import SURFACE_CORPUS, run_discovery_recette

GITLAB = SURFACE_CORPUS["gitlab"]

DETECTED = ["gl-readonly-reporter", "gl-pr-bot", "gl-admin-overreach"]
ALL = [*DETECTED, "gl-no-agent"]


def _gt(slug: str) -> dict:
    return json.loads((GITLAB / slug / "discovery-ground-truth.json").read_text(encoding="utf-8"))


def _scan(slug: str):
    a = ReferenceSourceScanAdapter()
    sid = a.register(str(GITLAB / slug / "repo"))
    a.await_run(a.scan(sid))
    return a.risks(sid)


class TestGitlabReferenceScan(unittest.TestCase):
    def test_detection_matches_ground_truth(self):
        for slug in ALL:
            with self.subTest(slug=slug):
                self.assertEqual(len(_scan(slug)) > 0, _gt(slug)["detected"])

    def test_action_pattern_coverage(self):
        for slug in DETECTED:
            with self.subTest(slug=slug):
                got = {r.action_pattern for r in _scan(slug)}
                self.assertEqual(got, set(_gt(slug)["action_patterns"]))

    def test_target_system_is_gitlab(self):
        for slug in DETECTED:
            with self.subTest(slug=slug):
                self.assertTrue(all(r.target_system == "gitlab" for r in _scan(slug)))

    def test_policy_presence_matches_ground_truth(self):
        for slug in DETECTED:
            with self.subTest(slug=slug):
                present = any(bool(r.generated_policy) for r in _scan(slug))
                self.assertEqual(present, _gt(slug)["policy_generated"])

    def test_no_agent_is_true_negative(self):
        self.assertEqual(_scan("gl-no-agent"), [])


class TestGitlabHarness(unittest.TestCase):
    def test_full_gitlab_recette_passes(self):
        scorecard = run_discovery_recette(corpus_root=GITLAB)
        self.assertTrue(scorecard.all_passed, "\n" + scorecard.render())
        self.assertEqual(scorecard.false_positives, 0)
        self.assertEqual(scorecard.false_negatives, 0)
        self.assertTrue(scorecard.ordering_ok)


if __name__ == "__main__":
    unittest.main()
