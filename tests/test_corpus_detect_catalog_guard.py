"""Coverage guard for the detect + catalog corpus artifacts (R20).

These committed artifacts are single sources of truth consumed by BOTH the Rust
discovery engine and the Python API. A deleted, malformed, or inconsistent
artifact must turn THIS test red rather than fail silently somewhere downstream
(no-silent-recette-gaps). Pure stdlib + json (zero install).
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CATALOG = _REPO_ROOT / "corpus" / "catalog" / "agent-registry.json"
_SIGNATURES = _REPO_ROOT / "corpus" / "detect" / "observability-signatures.json"
_AGREEMENT = _REPO_ROOT / "corpus" / "detect" / "agreement-cases.json"
_REPOS = _REPO_ROOT / "corpus" / "detect" / "repos"

_CATEGORIES = {"tracing", "replay", "audit", "eval", "gateway"}
_EXPECTED_SIGNATURE_COUNT = 12


class TestCatalogCorpusGuard(unittest.TestCase):
    def test_catalog_registry_is_present_and_consistent(self) -> None:
        self.assertTrue(_CATALOG.is_file(), "corpus/catalog/agent-registry.json missing")
        data = json.loads(_CATALOG.read_text(encoding="utf-8"))
        entries = data.get("entries")
        self.assertIsInstance(entries, list)
        self.assertTrue(entries, "catalog registry must declare agents")
        names = [e["name"] for e in entries]
        self.assertEqual(len(names), len(set(names)), "duplicate agent names in catalog")


class TestDetectCorpusGuard(unittest.TestCase):
    def test_signature_table_is_present_and_well_formed(self) -> None:
        self.assertTrue(_SIGNATURES.is_file(), "observability-signatures.json missing")
        sigs = json.loads(_SIGNATURES.read_text(encoding="utf-8"))
        self.assertEqual(len(sigs), _EXPECTED_SIGNATURE_COUNT, "signature count drifted")
        tools = [s["tool"] for s in sigs]
        self.assertEqual(len(tools), len(set(tools)), "duplicate tool in signatures")
        for sig in sigs:
            self.assertIn(sig["category"], _CATEGORIES, f"bad category for {sig['tool']}")
            self.assertTrue(sig["needles"], f"{sig['tool']} has no needles")
            caps = sig["capabilities"]
            self.assertTrue(caps, f"{sig['tool']} has no capabilities")
            self.assertEqual(caps, sorted(caps), f"capabilities not sorted for {sig['tool']}")
            self.assertEqual(len(caps), len(set(caps)), f"dup capability for {sig['tool']}")
            self.assertTrue(set(caps) <= _CATEGORIES, f"bad capability for {sig['tool']}")
            self.assertIn(sig["category"], caps, f"primary category absent from caps {sig['tool']}")

    def test_agreement_cases_are_present(self) -> None:
        self.assertTrue(_AGREEMENT.is_file(), "agreement-cases.json missing")
        cases = json.loads(_AGREEMENT.read_text(encoding="utf-8"))
        self.assertTrue(cases, "agreement cases must not be empty")
        for case in cases:
            self.assertIn("text", case)
            self.assertIn("expected", case)

    def test_repo_fixtures_each_carry_ground_truth(self) -> None:
        self.assertTrue(_REPOS.is_dir(), "corpus/detect/repos missing")
        dirs = [p for p in _REPOS.iterdir() if p.is_dir()]
        self.assertTrue(dirs, "expected at least one repo fixture")
        for repo in dirs:
            self.assertTrue(
                (repo / "expected.json").is_file(),
                f"repo fixture {repo.name} missing expected.json",
            )
            sources = [p for p in repo.iterdir() if p.is_file() and p.name != "expected.json"]
            self.assertTrue(sources, f"repo fixture {repo.name} has no source files")


if __name__ == "__main__":
    unittest.main()
