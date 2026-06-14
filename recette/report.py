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
from .maf_harness import run_maf_recette
from .maf_orchestration_harness import run_orchestration_recette
from .scorecard import Scorecard


@dataclass
class FullReport:
    identification: Scorecard
    discovery: dict[str, DiscoveryScorecard]
    maf: Scorecard
    orchestration: Scorecard

    @property
    def all_passed(self) -> bool:
        return (
            self.identification.all_passed
            and self.maf.all_passed
            and self.orchestration.all_passed
            and all(s.all_passed for s in self.discovery.values())
        )

    def to_dict(self) -> dict:
        i = self.identification
        m = self.maf
        o = self.orchestration
        return {
            "identification": {
                "agents": i.total,
                "passed": i.passed_count,
                "false_positives": i.false_positives,
                "false_negatives": i.false_negatives,
                "all_passed": i.all_passed,
            },
            "maf": {
                "agents": m.total,
                "passed": m.passed_count,
                "false_positives": m.false_positives,
                "false_negatives": m.false_negatives,
                "all_passed": m.all_passed,
            },
            "orchestration": {
                "teams": o.total,
                "passed": o.passed_count,
                "false_positives": o.false_positives,
                "false_negatives": o.false_negatives,
                "all_passed": o.all_passed,
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
        lines = ["=== inspect_ia_agents Recette -- Aggregate Report ===", ""]
        lines.append(
            f"identification : {i.passed_count}/{i.total} agents  "
            f"FP={i.false_positives} FN={i.false_negatives}  "
            f"{'PASS' if i.all_passed else 'FAIL'}"
        )
        m = self.maf
        lines.append(
            f"maf            : {m.passed_count}/{m.total} subjects  "
            f"FP={m.false_positives} FN={m.false_negatives}  "
            f"{'PASS' if m.all_passed else 'FAIL'}"
        )
        o = self.orchestration
        lines.append(
            f"orchestration  : {o.passed_count}/{o.total} teams  "
            f"FP={o.false_positives} FN={o.false_negatives}  "
            f"{'PASS' if o.all_passed else 'FAIL'}"
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
    return FullReport(
        identification=ident,
        discovery=discovery,
        maf=run_maf_recette(),
        orchestration=run_orchestration_recette(),
    )
