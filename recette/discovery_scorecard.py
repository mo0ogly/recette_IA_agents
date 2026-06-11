"""Discovery scorecard: scores scanner output against ground-truth on invariant properties.

Checks R1-R8 from the plan: detection, count/dedup, action coverage, target_system,
relative risk ordering (cross-corpus), scan determinism, policy presence, and the
false-positive / false-negative tallies. Never compares opaque values
(canonical_agent_id, exact risk score).
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Per-repo dimensions that participate in aggregate accuracy.
_DIMS = ("detection", "count", "actions", "target", "policy", "determinism")


@dataclass
class DiscoveryRepoResult:
    repo: str
    detected_expected: bool
    detected_actual: bool
    matches: dict[str, bool]  # only the applicable dimensions for this repo
    false_positive: bool = False
    false_negative: bool = False
    detail: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(self.matches.values())


@dataclass
class DiscoveryScorecard:
    results: list[DiscoveryRepoResult] = field(default_factory=list)
    ordering_ok: bool = True
    ordering_detail: str = ""

    def add(self, r: DiscoveryRepoResult) -> None:
        self.results.append(r)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed_count(self) -> int:
        return sum(1 for r in self.results if r.passed)

    def dimension_accuracy(self, dim: str) -> float:
        applicable = [r for r in self.results if dim in r.matches]
        if not applicable:
            return 0.0
        return sum(1 for r in applicable if r.matches[dim]) / len(applicable)

    @property
    def detection_rate(self) -> float:
        return self.dimension_accuracy("detection")

    @property
    def false_positives(self) -> int:
        return sum(1 for r in self.results if r.false_positive)

    @property
    def false_negatives(self) -> int:
        return sum(1 for r in self.results if r.false_negative)

    @property
    def all_passed(self) -> bool:
        return self.total > 0 and self.passed_count == self.total and self.ordering_ok

    def render(self) -> str:
        failed = self.total - self.passed_count
        lines: list[str] = []
        lines.append("=== AgentRail Discovery Recette Scorecard ===")
        lines.append(f"repos: {self.total}  passed: {self.passed_count}  failed: {failed}")
        lines.append("")
        header = f"{'repo':24} " + " ".join(f"{d[:4]:>5}" for d in _DIMS)
        lines.append(header)
        lines.append("-" * len(header))
        for r in self.results:
            cells = " ".join(
                ("  ok " if r.matches.get(d) else (" MISS" if d in r.matches else "  -  "))
                for d in _DIMS
            )
            flag = "" if r.passed else "  <- FAIL"
            lines.append(f"{r.repo:24} {cells}{flag}")
            for d in r.detail:
                lines.append(f"    - {d}")
        lines.append("")
        for d in _DIMS:
            lines.append(f"  {d:12} {self.dimension_accuracy(d) * 100:6.1f}%")
        lines.append(
            f"risk ordering : {'OK' if self.ordering_ok else 'BROKEN -- ' + self.ordering_detail}"
        )
        lines.append(
            f"false positives: {self.false_positives}  (agent reported in a no-agent repo)"
        )
        lines.append(
            f"false negatives: {self.false_negatives}  (agent missed in a real-agent repo)"
        )
        lines.append("")
        lines.append(
            "VERDICT: "
            + (
                "PASS -- scanner matches ground-truth on all repos"
                if self.all_passed
                else "FAIL -- see MISS / ordering above"
            )
        )
        return "\n".join(lines)
