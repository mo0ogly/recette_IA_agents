"""Scorecard: compares tool output against ground-truth and aggregates metrics."""

from __future__ import annotations

from dataclasses import dataclass, field

_DIMENSIONS = ("detection", "identity", "capabilities", "policy", "behavior", "verdict")


@dataclass
class AgentResult:
    agent_id: str
    category: str  # correct | incorrect (from ground-truth)
    matches: dict[str, bool]  # per-dimension: did the tool match ground-truth?
    predicted_verdict: str
    expected_verdict: str

    @property
    def passed(self) -> bool:
        return all(self.matches.values())


@dataclass
class Scorecard:
    results: list[AgentResult] = field(default_factory=list)

    def add(self, result: AgentResult) -> None:
        self.results.append(result)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed_count(self) -> int:
        return sum(1 for r in self.results if r.passed)

    def dimension_accuracy(self, dim: str) -> float:
        if not self.results:
            return 0.0
        ok = sum(1 for r in self.results if r.matches.get(dim, False))
        return ok / len(self.results)

    @property
    def detection_rate(self) -> float:
        return self.dimension_accuracy("detection")

    @property
    def false_positives(self) -> int:
        # Predicted incorrect, but ground-truth says correct.
        return sum(
            1
            for r in self.results
            if r.expected_verdict == "correct" and r.predicted_verdict == "incorrect"
        )

    @property
    def false_negatives(self) -> int:
        # Predicted correct, but ground-truth says incorrect.
        return sum(
            1
            for r in self.results
            if r.expected_verdict == "incorrect" and r.predicted_verdict == "correct"
        )

    @property
    def all_passed(self) -> bool:
        return self.total > 0 and self.passed_count == self.total

    def render(self) -> str:
        lines: list[str] = []
        lines.append("=== AgentRail Recette Scorecard ===")
        lines.append(f"agents: {self.total}  passed: {self.passed_count}  failed: {self.total - self.passed_count}")
        lines.append("")
        header = f"{'agent_id':32} {'cat':9} " + " ".join(f"{d[:4]:>5}" for d in _DIMENSIONS)
        lines.append(header)
        lines.append("-" * len(header))
        for r in self.results:
            cells = " ".join(("  ok " if r.matches.get(d, False) else " MISS") for d in _DIMENSIONS)
            flag = "" if r.passed else "  <- FAIL"
            lines.append(f"{r.agent_id:32} {r.category:9} {cells}{flag}")
        lines.append("")
        lines.append("per-dimension accuracy:")
        for d in _DIMENSIONS:
            lines.append(f"  {d:12} {self.dimension_accuracy(d) * 100:6.1f}%")
        lines.append(f"detection rate : {self.detection_rate * 100:.1f}%")
        lines.append(f"false positives: {self.false_positives}  (correct agent flagged incorrect)")
        lines.append(f"false negatives: {self.false_negatives}  (incorrect agent passed as correct)")
        lines.append("")
        lines.append("VERDICT: " + ("PASS -- tool matches ground-truth on all agents" if self.all_passed else "FAIL -- see MISS cells above"))
        return "\n".join(lines)
