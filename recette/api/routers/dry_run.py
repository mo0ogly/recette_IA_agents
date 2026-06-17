"""Dry-run endpoint: execute an agent's mock scenario without persisting.

A pre-create preview for the console wizard. The agent config is sent inline
(it need not be saved yet); the scenario runs in-memory against the lab forge
and the resulting action log is returned. Nothing is written to the event store
or the run history (I1), no external system is touched (I5), and the run is
deterministic (I4). Real-AI agents are rejected (mock-only).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..runners import dry_run_lane_b

router = APIRouter(prefix="/runs", tags=["runs"])


@router.post("/dry-run")
def post_dry_run(agent: dict) -> dict:
    """Run the inline agent's mock scenario and return its action log. 400 on
    invalid input (missing fields, real-AI agent, or no scenario)."""
    try:
        return dry_run_lane_b(agent)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
