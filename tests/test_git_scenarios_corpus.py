"""Q3 -- corpus gate for the seeded git red-team scenarios.

Every corpus/sim/*.git-scenario.json must validate as a git_sim_scenario, its
target_manifest must validate as a manifest, and run_git_scenario must catch the
anomaly (anomaly_caught True). The corpus carries a positive AND a negative, and
each negative is mono-axis: the runner's derived violation_type matches the
scenario's declared expected.violation_type (recette-corpus orthogonality rule).
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from recette.manifest import validate
from recette.redteam_git import run_git_scenario

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SIM_DIR = _REPO_ROOT / "corpus" / "sim"


def _git_scenarios() -> list[tuple[Path, dict]]:
    paths = sorted(_SIM_DIR.glob("*.git-scenario.json"))
    return [(p, json.loads(p.read_text(encoding="utf-8"))) for p in paths]


class TestGitScenariosCorpus(unittest.TestCase):
    def setUp(self) -> None:
        self.scenarios = _git_scenarios()
        self.assertTrue(self.scenarios, "no corpus/sim/*.git-scenario.json found")

    def test_each_scenario_validates_as_git_sim_scenario(self) -> None:
        for path, scenario in self.scenarios:
            with self.subTest(scenario=path.name):
                self.assertEqual(validate("git_sim_scenario", scenario), [])

    def test_each_target_manifest_validates_as_manifest(self) -> None:
        for path, scenario in self.scenarios:
            with self.subTest(scenario=path.name):
                self.assertEqual(validate("manifest", scenario["target_manifest"]), [])

    def test_each_scenario_catches_its_anomaly(self) -> None:
        for path, scenario in self.scenarios:
            with self.subTest(scenario=path.name):
                out = run_git_scenario(scenario)
                self.assertTrue(out.anomaly_caught, f"{path.name} did not catch its anomaly")

    def test_corpus_has_a_positive_and_a_negative(self) -> None:
        verdicts = {s["expected"]["verdict"] for _, s in self.scenarios}
        self.assertIn("correct", verdicts, "corpus has no positive (expected correct) git scenario")
        self.assertIn(
            "incorrect", verdicts, "corpus has no negative (expected incorrect) git scenario"
        )

    def test_negatives_are_mono_axis(self) -> None:
        for path, scenario in self.scenarios:
            if scenario["expected"]["verdict"] != "incorrect":
                continue
            with self.subTest(scenario=path.name):
                out = run_git_scenario(scenario)
                self.assertEqual(
                    out.violation_type,
                    scenario["expected"]["violation_type"],
                    f"{path.name}: judged violation_type does not match declared expectation",
                )


if __name__ == "__main__":
    unittest.main()
