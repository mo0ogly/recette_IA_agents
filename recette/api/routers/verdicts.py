"""Verdict ingestion: external tools submit results, the API judges them.

POST /verdicts compares each submitted result against the agent's stored
ground_truth block and persists the judged submission. Fail-safe: a malformed
result entry or an unknown agent yields a judged FAIL entry with an error
field, never a 500 (the rest of the submission is still judged).

Evidence: each judged entry carries the event ids of the agent's audit-log
events at submission time, plus the submission-level submitted_seq (the max
event-store seq when the verdict was received). Both come from the append-only
store, never from the clock (I4).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ..verdict_store import judge

router = APIRouter(prefix="/verdicts", tags=["verdicts"])

_DIMENSIONS = ("identity", "capabilities", "policy", "behavior")


def _rate(hits: int, n: int) -> float | None:
    """Plain fraction rounded to 4 decimals; null when nothing was checked."""
    if n == 0:
        return None
    return round(hits / n, 4)


def _judge_one(request: Request, result: object) -> dict:
    if not isinstance(result, dict):
        return {"agent_id": None, "status": "FAIL", "error": "malformed result entry"}
    agent_id = result.get("agent_id")
    if not isinstance(agent_id, str) or not agent_id:
        return {"agent_id": agent_id, "status": "FAIL", "error": "missing agent_id"}
    agent = request.app.state.config_store.get_agent(agent_id)
    if agent is None:
        return {"agent_id": agent_id, "status": "FAIL", "error": "unknown agent"}
    if "ground_truth" not in agent:
        return {"agent_id": agent_id, "status": "SKIP"}
    evidence_event_ids = [
        e.event_id for e in request.app.state.event_store.read_from(0, agent_id=agent_id)
    ]
    return {"agent_id": agent_id, **judge(agent["ground_truth"], result, evidence_event_ids)}


@router.post("")
def submit_verdicts(request: Request, body: dict[str, Any]) -> dict:
    results = body.get("results")
    if not isinstance(results, list):
        raise HTTPException(status_code=400, detail="'results' must be a list")
    judged = [_judge_one(request, result) for result in results]
    # Max seq of the append-only log at submission time (0 when empty). The
    # store exposes no max-seq accessor, so read the last event's seq.
    events = request.app.state.event_store.read_from(0)
    submitted_seq = events[-1].seq if events else 0
    request.app.state.verdict_store.append(
        {
            "tool": body.get("tool"),
            "results": results,
            "judged": judged,
            "submitted_seq": submitted_seq,
        }
    )
    return {"judged": judged, "submitted_seq": submitted_seq}


@router.get("")
def latest_submission(request: Request) -> dict:
    latest = request.app.state.verdict_store.latest()
    if latest is None:
        raise HTTPException(status_code=404, detail="no verdict submission yet")
    return latest


@router.get("/history")
def submission_history(request: Request) -> list[dict]:
    return request.app.state.verdict_store.history()


@router.get("/scorecard")
def scorecard(request: Request) -> dict:
    """Deterministic aggregates over the latest judged submission (I4).

    Rates are plain fractions over the agents that actually carry the check
    (round(x, 4)); null when no agent carries it. FP/FN are detection-axis
    counters read from the persisted expected/observed pairs: FP = tool said
    detected on a ground-truth non-detectable agent, FN = the reverse.
    """
    latest = request.app.state.verdict_store.latest()
    if latest is None:
        raise HTTPException(status_code=404, detail="no verdict submission yet")
    judged = latest.get("judged") or []

    detected_checks: list[bool] = []
    dimension_checks: dict[str, list[bool]] = {dim: [] for dim in _DIMENSIONS}
    false_positives = 0
    false_negatives = 0
    for entry in judged:
        checks = entry.get("checks") or {}
        if "detected" in checks:
            detected_checks.append(bool(checks["detected"]))
        for dim in _DIMENSIONS:
            if f"dimension:{dim}" in checks:
                dimension_checks[dim].append(bool(checks[f"dimension:{dim}"]))
        expected = entry.get("expected") or {}
        observed = entry.get("observed") or {}
        if expected.get("detectable") is False and observed.get("detected") is True:
            false_positives += 1
        if expected.get("detectable") is True and observed.get("detected") is False:
            false_negatives += 1

    return {
        "total": len(judged),
        "passed": sum(1 for e in judged if e.get("status") == "PASS"),
        "skipped": sum(1 for e in judged if e.get("status") == "SKIP"),
        "detection_rate": _rate(sum(detected_checks), len(detected_checks)),
        "accuracy_by_dimension": {
            dim: _rate(sum(values), len(values)) for dim, values in dimension_checks.items()
        },
        "false_positives": false_positives,
        "false_negatives": false_negatives,
    }
