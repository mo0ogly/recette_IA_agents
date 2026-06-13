"""Benchmark harness: per-dimension / per-style judge accuracy over the corpus."""

from __future__ import annotations

import unittest

from recette.benchmark import full_benchmark, orchestration_benchmark, render

_DIMS = ("identity", "capabilities", "policy", "behavior")


class TestOrchestrationBenchmark(unittest.TestCase):
    def setUp(self) -> None:
        self.bench = orchestration_benchmark()

    def test_overall_shape(self) -> None:
        self.assertGreaterEqual(self.bench["total"], 13)
        self.assertEqual(set(self.bench["dimension_accuracy"]), set(_DIMS))

    def test_every_style_present_and_accurate(self) -> None:
        styles = set(self.bench["by_style"])
        self.assertEqual(
            styles, {"handoff", "sequential", "concurrent", "group_chat", "magentic"}
        )
        # The committed corpus is the ground-truth, so the reference judge scores
        # 100% accuracy on every dimension of every style.
        for area in self.bench["by_style"].values():
            for d in _DIMS:
                self.assertEqual(area["dimension_accuracy"][d], 1.0)

    def test_overall_accuracy_is_one(self) -> None:
        for d in _DIMS:
            self.assertEqual(self.bench["dimension_accuracy"][d], 1.0)
        self.assertEqual(self.bench["passed"], self.bench["total"])


class TestFullBenchmark(unittest.TestCase):
    def test_areas_and_render(self) -> None:
        bench = full_benchmark()
        self.assertEqual(set(bench), {"identification", "maf", "orchestration"})
        for area in ("identification", "maf"):
            self.assertIn("dimension_accuracy", bench[area])
        text = render(bench)
        self.assertIn("Benchmark", text)
        self.assertIn("orchestration by style", text)
        self.assertIn("magentic", text)


if __name__ == "__main__":
    unittest.main()
