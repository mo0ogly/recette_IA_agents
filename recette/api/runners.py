"""U1 run bodies — thin wrappers that reuse recette and emit event frames.

A runner has signature runner(params, emit, should_stop) -> None, where
emit(type: str, data: dict) records one frame and should_stop() -> bool is cooperative.
Runners never touch HTTP or asyncio — they are pure orchestration over recette.
"""

from __future__ import annotations

from collections.abc import Callable

from ..adapters import ReferenceDiscoveryAdapter, ReferenceIdentificationAdapter
from ..discovery_harness import (
    SURFACE_CORPUS,
    SURFACE_ORDER,
    discover_repo_dirs,
    run_discovery_recette,
)
from ..harness import discover_agent_dirs
from ..harness import run_agent as run_ident_agent
from ..scorecard import Scorecard

Emit = Callable[[str, dict], None]
ShouldStop = Callable[[], bool]


def identification_runner(params: dict, emit: Emit, should_stop: ShouldStop) -> None:
    disc = ReferenceDiscoveryAdapter()
    ident = ReferenceIdentificationAdapter()
    scorecard = Scorecard()
    for d in discover_agent_dirs():
        if should_stop():
            return
        result = run_ident_agent(d, discovery=disc, identification=ident)
        scorecard.add(result)
        emit(
            "agent_result",
            {
                "agent_id": result.agent_id,
                "passed": result.passed,
                "predicted_verdict": result.predicted_verdict,
                "expected_verdict": result.expected_verdict,
            },
        )
    emit("scorecard", _scorecard_data(scorecard))


def discovery_runner(params: dict, emit: Emit, should_stop: ShouldStop) -> None:
    surface = params.get("surface", "all")
    surfaces = (
        [s for s in SURFACE_ORDER if discover_repo_dirs(SURFACE_CORPUS[s])]
        if surface == "all"
        else [surface]
    )
    for s in surfaces:
        if should_stop():
            return
        sc = run_discovery_recette(corpus_root=SURFACE_CORPUS[s])
        emit(
            "scorecard",
            {
                "surface": s,
                "total": sc.total,
                "passed": sc.passed_count,
                "false_positives": sc.false_positives,
                "false_negatives": sc.false_negatives,
                "all_passed": sc.all_passed,
            },
        )


def _scorecard_data(sc: Scorecard) -> dict:
    return {
        "total": sc.total,
        "passed": sc.passed_count,
        "false_positives": sc.false_positives,
        "false_negatives": sc.false_negatives,
        "detection_rate": sc.detection_rate,
        "all_passed": sc.all_passed,
    }
