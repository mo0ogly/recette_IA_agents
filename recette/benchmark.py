"""Benchmark / eval harness: aggregate metrics beyond pass/fail (AF Labs analog).

Where the scorecard answers "did every subject match its ground-truth?", the
benchmark answers "how accurate is the judge per dimension, per style, per area?"
-- the metrics you compare across corpora or judge versions. Built on the same
deterministic judges (I4); pure aggregation over the committed corpus.
"""

from __future__ import annotations

from collections import defaultdict

from .maf_orchestration_harness import discover_orchestration_dirs, judge_dir
from .manifest import load_validated
from .scorecard import Scorecard

_DIMS = ("identity", "capabilities", "policy", "behavior")


def _area(scorecard: Scorecard) -> dict:
    return {
        "total": scorecard.total,
        "passed": scorecard.passed_count,
        "false_positives": scorecard.false_positives,
        "false_negatives": scorecard.false_negatives,
        "dimension_accuracy": {d: scorecard.dimension_accuracy(d) for d in _DIMS},
    }


def orchestration_benchmark() -> dict:
    """Per-style and overall judge accuracy over the orchestration corpus."""
    overall = Scorecard()
    by_style: dict[str, Scorecard] = defaultdict(Scorecard)
    for d in discover_orchestration_dirs():
        team = load_validated("maf_orchestration", d / "team.json")
        result = judge_dir(d)
        overall.add(result)
        by_style[team.get("style", "handoff")].add(result)
    return {
        **_area(overall),
        "by_style": {style: _area(sc) for style, sc in sorted(by_style.items())},
    }


def full_benchmark() -> dict:
    """Consolidated benchmark across the identification, MAF and orchestration areas."""
    from .harness import DEFAULT_CORPUS, run_recette
    from .maf_harness import run_maf_recette

    return {
        "identification": _area(run_recette(DEFAULT_CORPUS)),
        "maf": _area(run_maf_recette()),
        "orchestration": orchestration_benchmark(),
    }


def render(benchmark: dict) -> str:
    lines = ["=== inspect_ia_agents Benchmark (judge accuracy) ===", ""]
    for area in ("identification", "maf", "orchestration"):
        a = benchmark[area]
        acc = "  ".join(f"{d[:3]}={a['dimension_accuracy'][d]:.2f}" for d in _DIMS)
        lines.append(f"{area:15} {a['passed']}/{a['total']}  {acc}")
    lines.append("")
    lines.append("orchestration by style:")
    for style, a in benchmark["orchestration"]["by_style"].items():
        acc = "  ".join(f"{d[:3]}={a['dimension_accuracy'][d]:.2f}" for d in _DIMS)
        lines.append(f"  {style:11} {a['passed']}/{a['total']}  {acc}")
    return "\n".join(lines)
