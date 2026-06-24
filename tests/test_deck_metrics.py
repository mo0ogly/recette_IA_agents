"""Deck metrics emitter: the numbers are derived from code, not hand-typed.

These tests pin the structural invariants (totals equal their parts, keys are
present, values are ints) so the emitter stays a trustworthy single source of
truth for the presentation deck. They do NOT freeze the exact corpus counts --
those legitimately grow; the coverage guard owns corpus completeness.
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_collect() -> Any:
    """Import scripts/deck_metrics.py by path (scripts/ is not a package)."""
    spec = importlib.util.spec_from_file_location(
        "deck_metrics", _REPO_ROOT / "scripts" / "deck_metrics.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.collect


class TestDeckMetrics(unittest.TestCase):
    def setUp(self) -> None:
        self.collect = _load_collect()
        self.m = self.collect()

    def test_has_all_expected_keys(self) -> None:
        expected = {
            "actions",
            "systems",
            "templates",
            "template_profiles",
            "template_systems",
            "providers",
            "annex_c_total",
            "annex_c_by_level",
            "discovery_total",
            "discovery_per_surface",
            "redteam_total",
            "redteam_maf",
            "redteam_git",
            "identification_subjects",
            "campaigns",
            "agents_runtime",
            "servers",
            "ai_backends",
        }
        self.assertTrue(expected.issubset(self.m.keys()))

    def test_scalar_counts_are_non_negative_ints(self) -> None:
        for key in ("actions", "systems", "templates", "providers", "campaigns"):
            self.assertIsInstance(self.m[key], int)
            self.assertGreater(self.m[key], 0)

    def test_annex_c_total_equals_sum_of_levels(self) -> None:
        self.assertEqual(self.m["annex_c_total"], sum(self.m["annex_c_by_level"].values()))

    def test_discovery_total_equals_sum_of_surfaces(self) -> None:
        self.assertEqual(self.m["discovery_total"], sum(self.m["discovery_per_surface"].values()))

    def test_redteam_total_equals_maf_plus_git(self) -> None:
        self.assertEqual(self.m["redteam_total"], self.m["redteam_maf"] + self.m["redteam_git"])

    def test_templates_total_equals_sum_of_profiles(self) -> None:
        self.assertEqual(self.m["templates"], sum(self.m["template_profiles"].values()))

    def test_deterministic(self) -> None:
        self.assertEqual(self.collect(), self.collect())


if __name__ == "__main__":
    unittest.main()
