"""Recette test suite. Pure stdlib unittest -- runs with zero installed deps
besides jsonschema (used by the package itself)."""

from __future__ import annotations

import unittest
from pathlib import Path

from recette import LabForge, ReferenceIdentificationAdapter, TestAgent, run_recette
from recette.adapters import DiscoveryResult, IdentificationResult
from recette.events import LogicalClock
from recette.harness import discover_agent_dirs
from recette.manifest import load_ground_truth, load_manifest, load_scenario
from recette.scorecard import Scorecard

REPO = Path(__file__).resolve().parent.parent
CORPUS = REPO / "corpus" / "agents"


class TestDeterminism(unittest.TestCase):
    def test_logical_clock_is_reproducible(self):
        a, b = LogicalClock(), LogicalClock()
        self.assertEqual([a.tick() for _ in range(3)], [b.tick() for _ in range(3)])

    def test_clock_has_no_wallclock(self):
        # First tick is the fixed epoch, never the host time.
        self.assertEqual(LogicalClock().tick(), "2023-11-14T22:13:20Z")

    def test_agent_run_is_byte_identical(self):
        agent = TestAgent.from_dir(CORPUS / "correct" / "gh-issue-triager")
        run_a = [x.to_dict() for x in agent.run(LabForge())]
        run_b = [x.to_dict() for x in agent.run(LabForge())]
        self.assertEqual(run_a, run_b)


class TestSchemas(unittest.TestCase):
    def test_every_corpus_artifact_validates(self):
        dirs = discover_agent_dirs(CORPUS)
        self.assertGreaterEqual(len(dirs), 10)
        for d in dirs:
            with self.subTest(agent=d.name):
                load_manifest(d / "manifest.json")
                load_scenario(d / "scenario.json")
                load_ground_truth(d / "ground-truth.json")

    def test_agent_id_consistent_across_files(self):
        for d in discover_agent_dirs(CORPUS):
            ids = {
                load_manifest(d / "manifest.json")["agent_id"],
                load_scenario(d / "scenario.json")["agent_id"],
                load_ground_truth(d / "ground-truth.json")["agent_id"],
            }
            self.assertEqual(len(ids), 1, f"{d.name}: {ids}")

    def test_incorrect_agents_carry_violation_type(self):
        for d in (CORPUS / "incorrect").iterdir():
            gt = load_ground_truth(d / "ground-truth.json")
            self.assertEqual(gt["category"], "incorrect")
            self.assertIn("violation_type", gt)


class TestCoverage(unittest.TestCase):
    def test_all_violation_types_on_both_platforms(self):
        wanted = {"identity_mismatch", "capability_overreach", "policy_violation", "behavior_anomaly"}
        seen: dict[str, set[str]] = {"github": set(), "gitlab": set()}
        for d in (CORPUS / "incorrect").iterdir():
            gt = load_ground_truth(d / "ground-truth.json")
            man = load_manifest(d / "manifest.json")
            for plat in man["target_systems"]:
                seen[plat].add(gt["violation_type"])
        self.assertEqual(seen["github"], wanted, f"github missing {wanted - seen['github']}")
        self.assertEqual(seen["gitlab"], wanted, f"gitlab missing {wanted - seen['gitlab']}")

    def test_at_least_one_correct_per_platform(self):
        plats = set()
        for d in (CORPUS / "correct").iterdir():
            plats |= set(load_manifest(d / "manifest.json")["target_systems"])
        self.assertIn("github", plats)
        self.assertIn("gitlab", plats)


class TestReferenceAdapterMatchesGroundTruth(unittest.TestCase):
    def test_full_recette_passes(self):
        scorecard = run_recette(CORPUS)
        self.assertTrue(scorecard.all_passed, "\n" + scorecard.render())
        self.assertEqual(scorecard.false_positives, 0)
        self.assertEqual(scorecard.false_negatives, 0)

    def test_each_negative_breaks_exactly_one_dimension(self):
        # Orthogonality: an incorrect agent's identification must differ from a
        # fully-correct profile on exactly one of the 4 dimensions.
        ident = ReferenceIdentificationAdapter()
        for d in (CORPUS / "incorrect").iterdir():
            agent = TestAgent.from_dir(d)
            res = ident.identify(manifest=agent.manifest, action_log=agent.run(LabForge()))
            broken = sum(
                1
                for ok in (
                    res.identity_match,
                    res.capabilities_conform,
                    res.policy_compliant,
                    res.behavior_expected,
                )
                if not ok
            )
            self.assertEqual(broken, 1, f"{d.name}: {broken} dimensions broken (want 1)")
            self.assertEqual(res.verdict, "incorrect")


class TestScorecardDetectsBadTool(unittest.TestCase):
    """Negative test: a broken identification tool MUST surface as false negatives."""

    def test_always_correct_tool_produces_false_negatives(self):
        class AlwaysCorrect:
            def identify(self, *, manifest, action_log) -> IdentificationResult:
                return IdentificationResult(True, True, [], True, True, "correct")

        class AlwaysDetect:
            def discover(self, action_log) -> DiscoveryResult:
                return DiscoveryResult(detected=True, signals=["api_traffic"])

        scorecard = run_recette(CORPUS, discovery=AlwaysDetect(), identification=AlwaysCorrect())
        self.assertFalse(scorecard.all_passed)
        # 8 incorrect agents passed as correct = 8 false negatives.
        self.assertEqual(scorecard.false_negatives, 8)
        self.assertEqual(scorecard.false_positives, 0)


class TestScorecardShape(unittest.TestCase):
    def test_empty_scorecard_rates(self):
        sc = Scorecard()
        self.assertEqual(sc.detection_rate, 0.0)
        self.assertEqual(sc.total, 0)
        self.assertFalse(sc.all_passed)


if __name__ == "__main__":
    unittest.main()
