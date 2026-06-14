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
