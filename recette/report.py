"""Aggregate recette report: identification + every discovery surface in one verdict.

A single release-gate command: runs the identification recette and the discovery recette
for every surface that has a corpus, then reports per-area pass/fail plus an overall
verdict. Text or JSON.
"""

from __future__ import annotations

from dataclasses import dataclass

from .discovery_harness import (
    SURFACE_CORPUS,
    SURFACE_ORDER,
    discover_repo_dirs,
    run_discovery_recette,
)
from .discovery_scorecard import DiscoveryScorecard
from .harness import DEFAULT_CORPUS, run_recette
from .scorecard import Scorecard


@dataclass
class FullReport:
    identification: Scorecard
    discovery: dict[str, DiscoveryScorecard]

    @property
    def all_passed(self) -> bool:
        return self.identification.all_passed and all(s.all_passed for s in self.discovery.values())

    def to_dict(self) -> dict:
        i = self.identification
        return {
            "identification": {
                "agents": i.total,
                "passed": i.passed_count,
                "false_positives": i.false_positives,
                "false_negatives": i.false_negatives,
                "all_passed": i.all_passed,
            },
            "discovery": {
                surface: {
                    "repos": sc.total,
                    "passed": sc.passed_count,
                    "false_positives": sc.false_positives,
                    "false_negatives": sc.false_negatives,
                    "ordering_ok": sc.ordering_ok,
                    "all_passed": sc.all_passed,
                }
                for surface, sc in self.discovery.items()
            },
            "all_passed": self.all_passed,
        }

    def render(self) -> str:
        i = self.identification
        lines = ["=== AgentRail Recette -- Aggregate Report ===", ""]
        lines.append(
            f"identification : {i.passed_count}/{i.total} agents  "
            f"FP={i.false_positives} FN={i.false_negatives}  "
            f"{'PASS' if i.all_passed else 'FAIL'}"
        )
        lines.append("")
        lines.append("discovery:")
        for surface in SURFACE_ORDER:
            sc = self.discovery.get(surface)
            if sc is None:
                continue
            lines.append(
                f"  {surface:9} {sc.passed_count}/{sc.total} repos  "
                f"FP={sc.false_positives} FN={sc.false_negatives}  "
                f"ordering={'ok' if sc.ordering_ok else 'BROKEN'}  "
                f"{'PASS' if sc.all_passed else 'FAIL'}"
            )
        lines.append("")
        lines.append("VERDICT: " + ("PASS -- all recettes green" if self.all_passed else "FAIL"))
        return "\n".join(lines)


def build_report() -> FullReport:
    ident = run_recette(DEFAULT_CORPUS)
    discovery: dict[str, DiscoveryScorecard] = {}
    for surface in SURFACE_ORDER:
        if discover_repo_dirs(SURFACE_CORPUS[surface]):
            discovery[surface] = run_discovery_recette(corpus_root=SURFACE_CORPUS[surface])
    return FullReport(identification=ident, discovery=discovery)
