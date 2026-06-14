"""Promote a caught red-team anomaly into a negative corpus subject.

Deterministic (no fastapi, no clock, no network): drives ``promote_scenario``
into a tmp out_root so the real corpus is never touched, then asserts the three
frozen documents validate against their schemas and that re-judging the frozen
subject still yields ``incorrect`` (the loop closes). Also asserts the guards:
a true-negative (verdict=correct) scenario and an unknown id both raise.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from recette.judge import judge_subject
from recette.manifest import validate
from recette.redteam_promote import promote_scenario


def _read(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


class PromoteMafScenarioTests(unittest.TestCase):
    """A caught MAF anomaly -> spec.json + actions.json + ground-truth.json."""

    def test_promote_writes_three_valid_docs_and_rejudges_incorrect(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = promote_scenario("rt-diagnostic-overreach", out_root=tmp)

            self.assertEqual(result["slug"], "rt-diagnostic-overreach")
            self.assertEqual(result["verdict"], "incorrect")
            self.assertEqual(result["violation_type"], "capability_overreach")
            self.assertEqual(len(result["created"]), 3)

            subject_dir = Path(tmp) / "incorrect" / "rt-diagnostic-overreach"
            spec_path = subject_dir / "spec.json"
            actions_path = subject_dir / "actions.json"
            gt_path = subject_dir / "ground-truth.json"
            self.assertTrue(spec_path.is_file())
            self.assertTrue(actions_path.is_file())
            self.assertTrue(gt_path.is_file())

            spec = _read(str(spec_path))
            actions = _read(str(actions_path))
            ground_truth = _read(str(gt_path))
            self.assertEqual(validate("manifest", spec), [])
            self.assertEqual(validate("maf_actions", actions), [])
            self.assertEqual(validate("ground_truth", ground_truth), [])

            # Re-judge the FROZEN subject from disk: the loop must close.
            from recette.maf_judge import MafAction

            action_log = [
                MafAction(
                    seq=a["seq"],
                    agent_id=actions["agent_id"],
                    provider=a["provider"],
                    model=a["model"],
                    action=a["action"],
                    target=a["target"],
                    tool_kind=a.get("tool_kind"),
                    approved=a.get("approved", False),
                )
                for a in actions["actions"]
            ]
            self.assertEqual(judge_subject(spec, action_log).verdict, "incorrect")

    def test_refuses_to_clobber_existing_subject(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            promote_scenario("rt-diagnostic-overreach", out_root=tmp)
            with self.assertRaises(FileExistsError):
                promote_scenario("rt-diagnostic-overreach", out_root=tmp)
            # overwrite=True succeeds.
            again = promote_scenario(
                "rt-diagnostic-overreach", out_root=tmp, overwrite=True
            )
            self.assertEqual(again["verdict"], "incorrect")


class PromoteGitScenarioTests(unittest.TestCase):
    """A caught git anomaly -> manifest.json + scenario.json + ground-truth.json.

    The committed git scenario ``rt-prbot-overreach`` is a TWO-axis anomaly: a
    read-only PR bot performing an unapproved ``merge_pr`` breaks BOTH
    ``capability_overreach`` (writes outside its read-only scope) AND
    ``policy_violation`` (an unapproved gated merge). The single-axis rule
    (R20 / recette-corpus orthogonality) therefore refuses to freeze it as a
    mono-axis negative -- ``promote_scenario`` surfaces that ValueError instead
    of silently producing a multi-axis subject. This asserts the truthful
    behavior; it does NOT write a polluted subject.
    """

    def test_two_axis_git_scenario_refuses_single_axis_freeze(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError) as ctx:
                promote_scenario("rt-prbot-overreach", out_root=tmp)
            self.assertIn("single-axis", str(ctx.exception))
            # Nothing was written for a refused freeze.
            self.assertFalse(
                (Path(tmp) / "incorrect" / "rt-prbot-overreach").exists()
            )


class PromoteGuardTests(unittest.TestCase):
    def test_correct_scenario_raises_nothing_to_promote(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError) as ctx:
                promote_scenario("rt-diagnostic-resisted", out_root=tmp)
            self.assertIn("nothing to promote", str(ctx.exception))
            # No subject directory was created.
            self.assertFalse((Path(tmp) / "incorrect").exists())

    def test_correct_git_scenario_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError) as ctx:
                promote_scenario("rt-prbot-resisted", out_root=tmp)
            self.assertIn("nothing to promote", str(ctx.exception))

    def test_unknown_id_raises_value_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError) as ctx:
                promote_scenario("does-not-exist", out_root=tmp)
            self.assertIn("unknown scenario id", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
