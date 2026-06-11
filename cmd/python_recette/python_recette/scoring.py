"""Scoring: aggregate check results into per-bloc and global scores."""

from __future__ import annotations

from dataclasses import dataclass

from .model import CheckResult, Verdict

_BLOC_MAX: dict[str, float] = {"A": 10.0, "B": 10.0, "C": 10.0, "D": 5.0, "E": 4.0, "F": 5.0}
_NOMINAL_TOTAL = 44.0
_READY = 39.0
_CORRECTIONS = 30.0
_BLOCKING_VERDICT = "NE PAS INTEGRER. Refonte necessaire."


@dataclass
class BlocScore:
    """Per-bloc score breakdown."""

    bloc: str
    score: float
    max: float
    applicable: int
    passed: int

    def to_dict(self) -> dict[str, object]:
        """JSON-serializable representation."""
        return {
            "bloc": self.bloc,
            "score": round(self.score, 2),
            "max": self.max,
            "applicable": self.applicable,
            "passed": self.passed,
        }


@dataclass
class ScoreReport:
    """Full scoring report."""

    blocs: list[BlocScore]
    global_score: float
    global_max: float
    normalized_44: float
    critical_fails: int
    e_fail: bool
    f_violation: bool
    verdict: str

    def passes(self, min_score: int) -> bool:
        """True if the run meets ``min_score`` (/44) with no blocking failure."""
        return (
            self.critical_fails == 0
            and not self.e_fail
            and not self.f_violation
            and self.normalized_44 >= float(min_score)
        )

    def to_dict(self) -> dict[str, object]:
        """JSON-serializable representation."""
        return {
            "blocs": [b.to_dict() for b in self.blocs],
            "global": round(self.global_score, 2),
            "global_max": self.global_max,
            "normalized_44": round(self.normalized_44, 2),
            "critical_fails": self.critical_fails,
            "e_fail": self.e_fail,
            "f_violation": self.f_violation,
            "verdict": self.verdict,
        }


def score(results: list[CheckResult]) -> ScoreReport:
    """Compute the scoring report from all check results."""
    blocs: list[BlocScore] = []
    global_score = 0.0
    global_max = 0.0

    for bloc in ("A", "B", "C", "D", "E", "F"):
        in_bloc = [r for r in results if r.bloc == bloc]
        applicable = sum(1 for r in in_bloc if r.verdict is not Verdict.NA)
        passed = sum(1 for r in in_bloc if r.verdict is Verdict.PASS)
        bloc_max = _BLOC_MAX[bloc]
        if applicable == 0:
            bloc_score, counted_max = 0.0, 0.0
        else:
            bloc_score, counted_max = (passed / applicable) * bloc_max, bloc_max
        global_score += bloc_score
        global_max += counted_max
        blocs.append(BlocScore(bloc, bloc_score, counted_max, applicable, passed))

    normalized = (global_score / global_max * _NOMINAL_TOTAL) if global_max > 0 else 0.0
    critical_fails = sum(1 for r in results if r.is_critical_fail)
    e_fail = any(r.bloc == "E" and r.verdict is Verdict.FAIL for r in results)
    f_violation = any(r.bloc == "F" and r.verdict is Verdict.FAIL for r in results)

    return ScoreReport(
        blocs=blocs,
        global_score=global_score,
        global_max=global_max,
        normalized_44=normalized,
        critical_fails=critical_fails,
        e_fail=e_fail,
        f_violation=f_violation,
        verdict=_verdict(normalized, critical_fails, e_fail, f_violation),
    )


def _verdict(normalized: float, critical_fails: int, e_fail: bool, f_violation: bool) -> str:
    if critical_fails > 0 or e_fail or f_violation:
        return _BLOCKING_VERDICT
    if normalized >= _READY:
        return "Pret pour integration."
    if normalized >= _CORRECTIONS:
        return "Corrections requises avant integration."
    return _BLOCKING_VERDICT
