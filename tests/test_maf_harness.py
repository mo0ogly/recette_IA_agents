"""The on-disk MAF subject corpus is scored end-to-end: the judge's verdict matches
every subject's ground-truth, the corpus covers one correct subject plus each
violation_type, and each negative breaks exactly one dimension (orthogonality)."""

from __future__ import annotations

import json
import unittest

from recette.maf_harness import (
    DEFAULT_MAF_CORPUS,
    discover_maf_dirs,
    load_action_log,
    run_maf_recette,
)
from recette.maf_judge import judge_maf
from recette.manifest import load_validated

# Which judged dimension a violation_type must break.
_BREAKS = {
    "identity_mismatch": "identity",
    "capability_overreach": "capabilities",
    "policy_violation": "policy",
    "behavior_anomaly": "behavior",
}


class TestMafHarness(unittest.TestCase):
    def test_scorecard_matches_ground_truth_for_all_subjects(self) -> None:
        scorecard = run_maf_recette()
        self.assertGreater(scorecard.total, 0)
        self.assertTrue(scorecard.all_passed, scorecard.render())
        self.assertEqual(scorecard.false_positives, 0)
        self.assertEqual(scorecard.false_negatives, 0)

    def test_corpus_covers_correct_plus_each_violation_type(self) -> None:
        seen_correct = False
        violation_types: set[str] = set()
        for d in discover_maf_dirs():
            gt = json.loads((d / "ground-truth.json").read_text(encoding="utf-8"))
            if gt["category"] == "correct":
                seen_correct = True
            else:
                violation_types.add(gt["violation_type"])
        self.assertTrue(seen_correct)
        self.assertEqual(violation_types, set(_BREAKS))

    def test_each_negative_breaks_exactly_one_dimension(self) -> None:
        for d in discover_maf_dirs():
            gt = json.loads((d / "ground-truth.json").read_text(encoding="utf-8"))
            if gt["category"] != "incorrect":
                continue
            spec = load_validated("manifest", d / "spec.json")
            actions_doc = load_validated("maf_actions", d / "actions.json")
            r = judge_maf(spec, load_action_log(spec["agent_id"], actions_doc))
            judged = {
                "identity": r.identity_match,
                "capabilities": r.capabilities_conform,
                "policy": r.policy_compliant,
                "behavior": r.behavior_expected,
            }
            broken = [dim for dim, ok in judged.items() if not ok]
            self.assertEqual(
                broken,
                [_BREAKS[gt["violation_type"]]],
                f"{d.name}: expected only {_BREAKS[gt['violation_type']]} broken, got {broken}",
            )

    def test_default_corpus_path_exists(self) -> None:
        self.assertTrue(DEFAULT_MAF_CORPUS.is_dir())


if __name__ == "__main__":
    unittest.main()
