"""GET /discovery/check -- run the discovery recette and return per-repo detail.

Drives the reference source-scan adapter over the published test repos
(corpus/repos) and returns, per repo, whether discovery DETECTED the agent's
source form plus the invariant checks (detection, determinism, ordering). This is
what the console "Check discovery" button calls to show, in detail, that the
discovery tool finds each agent's source. Deterministic (I4), read-only.
"""

from __future__ import annotations

from fastapi import APIRouter

from ...discovery_harness import run_discovery_recette
from ...discovery_scorecard import DiscoveryScorecard

router = APIRouter(prefix="/discovery", tags=["discovery"])


def _serialize(card: DiscoveryScorecard) -> dict:
    return {
        "all_passed": card.all_passed,
        "total": card.total,
        "passed": card.passed_count,
        "detection_rate": card.detection_rate,
        "false_positives": card.false_positives,
        "false_negatives": card.false_negatives,
        "ordering_ok": card.ordering_ok,
        "repos": [
            {
                "repo": r.repo,
                "detected": r.detected_actual,
                "expected": r.detected_expected,
                "passed": r.passed,
                "false_positive": r.false_positive,
                "false_negative": r.false_negative,
                "detail": r.detail,
            }
            for r in card.results
        ],
    }


@router.get("/check")
def check() -> dict:
    """Run the discovery recette over corpus/repos and return the detailed result."""
    return _serialize(run_discovery_recette())
