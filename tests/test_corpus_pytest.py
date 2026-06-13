"""Pytest view of the recette corpus: one parametrized test per subject.

Mirrors langwatch/scenario's pytest integration -- each corpus subject becomes a
named pytest case (id = its slug), so `pytest -k <slug>` runs a single subject and
failures point at the exact one. Complements the unittest suite (this module
exposes bare functions, which unittest discovery ignores). Skips cleanly if pytest
is absent.
"""

from __future__ import annotations

try:
    import pytest

    HAVE_PYTEST = True
except ImportError:  # pragma: no cover - pytest is a dev dependency
    HAVE_PYTEST = False

from recette.maf_harness import discover_maf_dirs
from recette.maf_harness import judge_dir as judge_maf_dir
from recette.maf_orchestration_harness import discover_orchestration_dirs
from recette.maf_orchestration_harness import judge_dir as judge_orchestration_dir

if HAVE_PYTEST:
    _ORCH = discover_orchestration_dirs()
    _MAF = discover_maf_dirs()

    @pytest.mark.parametrize("subject", _ORCH, ids=[d.name for d in _ORCH])
    def test_orchestration_subject_matches_ground_truth(subject):  # type: ignore[no-untyped-def]
        result = judge_orchestration_dir(subject)
        assert all(result.matches.values()), f"{subject.name}: {result.matches}"

    @pytest.mark.parametrize("subject", _MAF, ids=[d.name for d in _MAF])
    def test_maf_subject_matches_ground_truth(subject):  # type: ignore[no-untyped-def]
        result = judge_maf_dir(subject)
        assert all(result.matches.values()), f"{subject.name}: {result.matches}"
