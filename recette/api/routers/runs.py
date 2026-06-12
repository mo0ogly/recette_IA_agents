"""U1: run launch/inspect/stop endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ..runners import discovery_runner, identification_runner

router = APIRouter(prefix="/runs", tags=["runs"])

_RUNNERS = {
    "identification": identification_runner,
    "discovery": discovery_runner,
}


@router.post("", status_code=201)
def launch(request: Request, body: dict[str, Any]) -> dict:
    kind = body.get("kind")
    if kind == "lane_b":
        raise HTTPException(status_code=400, detail="lane_b runs land in Task 8")
    runner = _RUNNERS.get(kind) if isinstance(kind, str) else None
    if runner is None:
        raise HTTPException(status_code=400, detail=f"unknown run kind {kind!r}")
    mgr = request.app.state.run_manager
    run = mgr.create(kind, body.get("params", {}))
    mgr.start(run, runner)
    return {"run_id": run.id, "status": run.status}


@router.get("/{run_id}")
def get_run(request: Request, run_id: str) -> dict:
    run = request.app.state.run_manager.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="no such run")
    return {"id": run.id, "kind": run.kind, "status": run.status, "error": run.error}


@router.get("/{run_id}/events")
def get_events(request: Request, run_id: str) -> list[dict]:
    run = request.app.state.run_manager.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="no such run")
    return list(run.events)


@router.post("/{run_id}/stop", status_code=202)
def stop_run(request: Request, run_id: str) -> dict:
    ok = request.app.state.run_manager.request_stop(run_id)
    if not ok:
        raise HTTPException(status_code=404, detail="no such run")
    return {"stopped": True}
