"""Structural + ground-truth tests for the realistic GitHub repo corpus."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import jsonschema

REPO = Path(__file__).resolve().parent.parent
REPOS = REPO / "corpus" / "repos"
GT_SCHEMA = json.loads(
    (REPO / "corpus" / "schemas" / "discovery-ground-truth.schema.json").read_text(encoding="utf-8")
)


def _repo_dirs():
    return sorted(
        p for p in REPOS.iterdir() if p.is_dir() and (p / "discovery-ground-truth.json").exists()
    )


class TestRepoCorpus(unittest.TestCase):
    def test_corpus_has_at_least_four_repos(self):
        self.assertGreaterEqual(len(_repo_dirs()), 4)

    def test_each_repo_has_publishable_tree_and_valid_ground_truth(self):
        validator = jsonschema.Draft202012Validator(GT_SCHEMA)
        for d in _repo_dirs():
            with self.subTest(repo=d.name):
                tree = d / "repo"
                self.assertTrue(tree.is_dir(), f"{d.name}: missing repo/ tree")
                self.assertTrue((tree / "README.md").exists(), f"{d.name}: repo/README.md missing")
                gt = json.loads((d / "discovery-ground-truth.json").read_text(encoding="utf-8"))
                validator.validate(gt)
                self.assertEqual(gt["agent_repo"], d.name, "agent_repo must match dir name")

    def test_detected_repos_have_agent_surface(self):
        # A discoverable agent must present at least one of: manifest, workflow, agent code.
        for d in _repo_dirs():
            gt = json.loads((d / "discovery-ground-truth.json").read_text(encoding="utf-8"))
            tree = d / "repo"
            surfaces = [
                (tree / ".agentrail" / "manifest.json").exists(),
                any((tree / ".github" / "workflows").glob("*.yml"))
                if (tree / ".github" / "workflows").is_dir()
                else False,
                (tree / "agent").is_dir(),
            ]
            with self.subTest(repo=d.name):
                if gt["detected"]:
                    self.assertTrue(
                        any(surfaces), f"{d.name}: detected agent has no scannable surface"
                    )

    def test_true_negative_present(self):
        negatives = [
            d
            for d in _repo_dirs()
            if not json.loads((d / "discovery-ground-truth.json").read_text(encoding="utf-8"))[
                "detected"
            ]
        ]
        self.assertGreaterEqual(len(negatives), 1, "corpus must include a true-negative repo")

    def test_risk_ranks_strictly_ordered(self):
        ranks = {
            d.name: json.loads((d / "discovery-ground-truth.json").read_text(encoding="utf-8")).get(
                "risk_rank", 0
            )
            for d in _repo_dirs()
        }
        # The three discoverable ranked repos must be strictly increasing.
        for low, high in [
            ("gh-readonly-reporter", "gh-pr-bot"),
            ("gh-pr-bot", "gh-admin-overreach"),
        ]:
            self.assertIn(low, ranks)
            self.assertIn(high, ranks)
            self.assertLess(ranks[low], ranks[high], f"{low} must rank below {high}")


if __name__ == "__main__":
    unittest.main()
