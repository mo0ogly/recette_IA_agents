"""Tests for the scoring aggregation."""

from __future__ import annotations

from python_recette import model
from python_recette.model import Severity
from python_recette.scoring import score


def test_na_checks_excluded_from_max() -> None:
    results = [
        model.passed("A1", "x", "A", Severity.CRITICAL),
        model.not_applicable("E1", "y", "E", Severity.CRITICAL, "manual"),
    ]
    report = score(results)
    bloc_e = next(b for b in report.blocs if b.bloc == "E")
    assert bloc_e.max == 0.0
    assert bloc_e.applicable == 0


def test_critical_fail_forces_blocking_verdict() -> None:
    results = [model.failed("A1", "x", "A", Severity.CRITICAL)]
    report = score(results)
    assert report.critical_fails == 1
    assert not report.passes(0)
    assert "NE PAS INTEGRER" in report.verdict


def test_all_pass_reaches_full_normalized_score() -> None:
    results = [
        model.passed("A1", "x", "A", Severity.CRITICAL),
        model.passed("B1", "y", "B", Severity.CRITICAL),
    ]
    report = score(results)
    assert abs(report.normalized_44 - 44.0) < 1e-9
    assert report.passes(39)
