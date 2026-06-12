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
