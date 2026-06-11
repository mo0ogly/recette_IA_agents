"""Tests for the offline oracle: ReferenceSourceScanAdapter over the repo corpus."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from recette.adapters import ReferenceSourceScanAdapter

REPO = Path(__file__).resolve().parent.parent
REPOS = REPO / "corpus" / "repos"


def _gt(slug: str) -> dict:
    return json.loads((REPOS / slug / "discovery-ground-truth.json").read_text(encoding="utf-8"))


def _scan(slug: str):
    a = ReferenceSourceScanAdapter()
    sid = a.register(str(REPOS / slug / "repo"))
    a.await_run(a.scan(sid))
    return a.risks(sid)


class TestReferenceScanReproducesGroundTruth(unittest.TestCase):
    def test_detection_matches_ground_truth(self):
        for slug in ["gh-readonly-reporter", "gh-pr-bot", "gh-admin-overreach", "gh-no-agent"]:
            with self.subTest(slug=slug):
                risks = _scan(slug)
                detected = len(risks) > 0
                self.assertEqual(detected, _gt(slug)["detected"])

    def test_action_pattern_coverage(self):
        for slug in ["gh-readonly-reporter", "gh-pr-bot", "gh-admin-overreach"]:
            with self.subTest(slug=slug):
                risks = _scan(slug)
                got = {r.action_pattern for r in risks}
                self.assertEqual(got, set(_gt(slug)["action_patterns"]))

    def test_single_canonical_id_per_repo(self):
        # One agent per repo => all its risks share one canonical_agent_id.
        for slug in ["gh-readonly-reporter", "gh-pr-bot", "gh-admin-overreach"]:
            ids = {r.canonical_agent_id for r in _scan(slug)}
            self.assertEqual(len(ids), 1, f"{slug}: expected 1 canonical id, got {ids}")

    def test_true_negative_yields_no_risks(self):
        self.assertEqual(_scan("gh-no-agent"), [])

    def test_relative_risk_ordering(self):
        def level(slug):
            return max(r.estimated_risk["level"] for r in _scan(slug))

        self.assertLess(level("gh-readonly-reporter"), level("gh-pr-bot"))
        self.assertLess(level("gh-pr-bot"), level("gh-admin-overreach"))

    def test_policy_presence(self):
        # Reporter (rank 1) -> no policy; pr-bot + admin -> policy emitted.
        self.assertTrue(
            all(r.generated_policy in (None, "") for r in _scan("gh-readonly-reporter"))
        )
        self.assertTrue(all(r.generated_policy for r in _scan("gh-pr-bot")))
        self.assertTrue(all(r.generated_policy for r in _scan("gh-admin-overreach")))

    def test_target_system_github(self):
        for slug in ["gh-readonly-reporter", "gh-pr-bot", "gh-admin-overreach"]:
            self.assertTrue(all(r.target_system == "github" for r in _scan(slug)))


class TestReferenceScanDeterminism(unittest.TestCase):
    def test_two_scans_identical(self):
        # Invariant 7: same repo => identical risk set across scans.
        for slug in ["gh-readonly-reporter", "gh-pr-bot", "gh-admin-overreach", "gh-no-agent"]:
            with self.subTest(slug=slug):
                a = [r.__dict__ for r in _scan(slug)]
                b = [r.__dict__ for r in _scan(slug)]
                self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
