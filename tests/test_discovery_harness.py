"""Tests for the discovery harness + scorecard against the repo corpus."""

from __future__ import annotations

import unittest

from recette.adapters import DiscoveryRisk, ReferenceSourceScanAdapter
from recette.discovery_harness import discover_repo_dirs, run_discovery_recette


class TestDiscoveryHarnessReference(unittest.TestCase):
    def test_reference_adapter_passes_full_corpus(self):
        sc = run_discovery_recette(ReferenceSourceScanAdapter())
        self.assertTrue(sc.all_passed, "\n" + sc.render())
        self.assertEqual(sc.false_positives, 0)
        self.assertEqual(sc.false_negatives, 0)
        self.assertTrue(sc.ordering_ok)

    def test_corpus_has_repos(self):
        self.assertGreaterEqual(len(discover_repo_dirs()), 4)

    def test_detection_rate_100(self):
        sc = run_discovery_recette(ReferenceSourceScanAdapter())
        self.assertEqual(sc.detection_rate, 1.0)


class _BlindScanner:
    """A broken scanner that finds nothing -- must surface as false negatives."""

    def register(self, location: str) -> str:
        return "x"

    def scan(self, source_id: str) -> str:
        return "r"

    def await_run(self, run_id: str) -> str:
        return "completed"

    def risks(self, source_id: str):
        return []


class _CredulousScanner:
    """A scanner that reports a fake agent everywhere -- must surface a false positive."""

    def register(self, location: str) -> str:
        return location

    def scan(self, source_id: str) -> str:
        return "r"

    def await_run(self, run_id: str) -> str:
        return "completed"

    def risks(self, source_id: str):
        return [DiscoveryRisk("fake", "push", "github", {"level": 3}, "p")]


class TestDiscoveryHarnessDetectsBadScanners(unittest.TestCase):
    def test_blind_scanner_produces_false_negatives(self):
        sc = run_discovery_recette(_BlindScanner())
        self.assertFalse(sc.all_passed)
        # 9 discoverable github repos missed = 9 false negatives (gh-pr-bot,
        # gh-readonly-reporter, gh-admin-overreach, gh-supply-chain-compromise,
        # gh-shadow-agent, gh-invalid-passport, gh-passport-expired,
        # gh-passport-tampered, gh-passport-scope-overreach).
        self.assertEqual(sc.false_negatives, 9)

    def test_credulous_scanner_produces_false_positive(self):
        sc = run_discovery_recette(_CredulousScanner())
        self.assertFalse(sc.all_passed)
        # gh-no-agent wrongly flagged = 1 false positive.
        self.assertEqual(sc.false_positives, 1)


if __name__ == "__main__":
    unittest.main()
