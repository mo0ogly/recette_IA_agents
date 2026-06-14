"""Tests for the aggregate report: identification + all discovery surfaces, one verdict."""

from __future__ import annotations

import unittest

from recette.discovery_harness import SURFACE_ORDER
from recette.report import build_report


class TestAggregateReport(unittest.TestCase):
    def setUp(self):
        self.report = build_report()

    def test_overall_passes(self):
        self.assertTrue(self.report.all_passed, "\n" + self.report.render())

    def test_covers_all_corpus_surfaces(self):
        # Every surface that has a corpus must appear in the report.
        for surface in ("github", "temporal", "openapi", "mcp"):
            with self.subTest(surface=surface):
                self.assertIn(surface, self.report.discovery)

    def test_identification_present(self):
        self.assertGreater(self.report.identification.total, 0)

    def test_maf_subjects_present_and_pass(self):
        # The unified report aggregates the standard-aligned (MAF) corpus too.
        self.assertGreater(self.report.maf.total, 0)
        self.assertTrue(self.report.maf.all_passed, "\n" + self.report.render())

    def test_to_dict_shape(self):
        d = self.report.to_dict()
        self.assertIn("identification", d)
        self.assertIn("discovery", d)
        self.assertIn("maf", d)
        self.assertGreater(d["maf"]["agents"], 0)
        self.assertTrue(d["all_passed"])
        for surface in self.report.discovery:
            self.assertIn(surface, SURFACE_ORDER)


if __name__ == "__main__":
    unittest.main()
