import json
import unittest
from pathlib import Path

from recette.manifest import validate
from recette.redteam_recette import _replay, run_scenario

SIM = Path(__file__).resolve().parent.parent / "corpus" / "sim"


class T(unittest.TestCase):
    def test_every_scenario_validates_and_matches_expected(self):
        files = sorted(SIM.glob("*.scenario.json"))
        self.assertTrue(files, "no scenarios committed")
        for f in files:
            data = json.loads(f.read_text())
            self.assertEqual(validate("sim_scenario", data), [], f.name)
            out = run_scenario(data)
            self.assertTrue(
                out.anomaly_caught,
                f"{f.name}: predicted {out.verdict} != expected {out.expected_verdict}",
            )

    def test_corpus_has_a_positive_and_a_negative(self):
        verdicts = {
            json.loads(f.read_text())["expected"]["verdict"] for f in SIM.glob("*.scenario.json")
        }
        self.assertIn("correct", verdicts)
        self.assertIn("incorrect", verdicts)

    def test_negatives_are_mono_axis(self):
        # Orthogonality gate (R20 / recette-corpus.md): a negative breaks EXACTLY
        # one of the four judge dimensions. violation_type alone is too weak --
        # _violation_of returns the FIRST broken dim, so a two-axis run passes
        # silently. Re-judge with _replay (the typed runner) and count how many
        # of the four booleans are False; it must be exactly one.
        for f in SIM.glob("*.scenario.json"):
            data = json.loads(f.read_text())
            if data["expected"]["verdict"] == "incorrect":
                _, _, verdict = _replay(data)
                broken = [
                    not verdict.identity_match,
                    not verdict.capabilities_conform,
                    not verdict.policy_compliant,
                    not verdict.behavior_expected,
                ]
                self.assertEqual(
                    sum(broken),
                    1,
                    f"{f.name}: negative must break EXACTLY one dimension "
                    f"(identity={verdict.identity_match}, "
                    f"capabilities={verdict.capabilities_conform}, "
                    f"policy={verdict.policy_compliant}, "
                    f"behavior={verdict.behavior_expected})",
                )
                out = run_scenario(data)
                self.assertIsNotNone(out.violation_type, f.name)
                self.assertEqual(
                    out.violation_type,
                    data["expected"].get("violation_type"),
                    f.name,
                )

    def test_handoff_overreach_seed_violation_names_a_handoff(self):
        # The handoff-overreach seed must break capabilities via an UNdeclared
        # handoff (not a tool): the judge's per-action violation must name the
        # handoff target so the UI marks the hop hors-perimetre from the JUDGE.
        f = SIM / "rt-maf-handoff-overreach.scenario.json"
        _, _, verdict = _replay(json.loads(f.read_text()))
        self.assertFalse(verdict.capabilities_conform)
        self.assertTrue(verdict.identity_match)
        self.assertTrue(verdict.policy_compliant)
        self.assertTrue(verdict.behavior_expected)
        self.assertEqual(len(verdict.capability_violations), 1)
        note = verdict.capability_violations[0]
        self.assertIn("handoff", note.observed_action)
        self.assertIn("remediation-agent", note.observed_action)

    def test_approval_bypass_seed_breaks_policy_only(self):
        # The approval-bypass seed must break EXACTLY the policy dimension (I6):
        # the declared approval=always tool is invoked but never approved under
        # the deny_all approver. Capabilities stay conform (the tool IS declared).
        f = SIM / "rt-maf-approval-bypass.scenario.json"
        _, _, verdict = _replay(json.loads(f.read_text()))
        self.assertFalse(verdict.policy_compliant)
        self.assertTrue(verdict.identity_match)
        self.assertTrue(verdict.capabilities_conform)
        self.assertTrue(verdict.behavior_expected)
        self.assertEqual(verdict.capability_violations, [])
