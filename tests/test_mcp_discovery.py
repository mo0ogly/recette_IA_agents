"""Tests for the Manifest/MCP discovery surface: oracle reproduces ground-truth + harness PASS.

Corpus = real .agentrail/manifest.json declarations (highest-precision surface). Asserts
invariant properties only.
"""

from __future__ import annotations

import json
import unittest

from recette.adapters import ReferenceSourceScanAdapter
from recette.discovery_harness import SURFACE_CORPUS, run_discovery_recette

MCP = SURFACE_CORPUS["mcp"]

DETECTED = ["mcp-readonly-reporter", "mcp-pr-bot", "mcp-admin-overreach"]
ALL = [*DETECTED, "mcp-no-agent"]


def _gt(slug: str) -> dict:
    return json.loads((MCP / slug / "discovery-ground-truth.json").read_text(encoding="utf-8"))


def _scan(slug: str):
    a = ReferenceSourceScanAdapter()
    sid = a.register(str(MCP / slug / "repo"))
    a.await_run(a.scan(sid))
    return a.risks(sid)


class TestMcpReferenceScan(unittest.TestCase):
    def test_detection_matches_ground_truth(self):
        for slug in ALL:
            with self.subTest(slug=slug):
                self.assertEqual(len(_scan(slug)) > 0, _gt(slug)["detected"])

    def test_action_pattern_coverage(self):
        for slug in DETECTED:
            with self.subTest(slug=slug):
                got = {r.action_pattern for r in _scan(slug)}
                self.assertEqual(got, set(_gt(slug)["action_patterns"]))

    def test_target_system_is_mcp(self):
        for slug in DETECTED:
            with self.subTest(slug=slug):
                self.assertTrue(all(r.target_system == "mcp" for r in _scan(slug)))

    def test_policy_presence_matches_ground_truth(self):
        for slug in DETECTED:
            with self.subTest(slug=slug):
                present = any(bool(r.generated_policy) for r in _scan(slug))
                self.assertEqual(present, _gt(slug)["policy_generated"])

    def test_no_agent_is_true_negative(self):
        self.assertEqual(_scan("mcp-no-agent"), [])


class TestMcpHarness(unittest.TestCase):
    def test_full_mcp_recette_passes(self):
        scorecard = run_discovery_recette(corpus_root=MCP)
        self.assertTrue(scorecard.all_passed, "\n" + scorecard.render())
        self.assertEqual(scorecard.false_positives, 0)
        self.assertEqual(scorecard.false_negatives, 0)
        self.assertTrue(scorecard.ordering_ok)


if __name__ == "__main__":
    unittest.main()
