"""U1: run launch/inspect/stop endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect

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
        store = request.app.state.config_store
        params = body.get("params", {})
        agent_cfg = store.get_agent(params.get("agent_id", ""))
        if agent_cfg is None:
            raise HTTPException(status_code=400, detail="unknown lane_b agent_id")
        from ...llm import LlmBackend
        from ..runners import build_stub_llm, make_lane_b_runner

        llm: LlmBackend
        if "stub_script" in params:
            llm = build_stub_llm(params["stub_script"])
        else:
            backend = store.get_ai_backend(agent_cfg["ai_backend_id"])
            if backend is None:
                raise HTTPException(status_code=400, detail="unknown ai_backend_id")
            from ...llm import build_llm

            llm = build_llm(backend["provider"], backend["model"])  # live; key from env (R8)
        mgr = request.app.state.run_manager
        run = mgr.create("lane_b", params)
        mgr.start(run, make_lane_b_runner(agent_cfg, llm))
        return {"run_id": run.id, "status": run.status}
    runner = _RUNNERS.get(kind) if isinstance(kind, str) else None
    if runner is None:
        raise HTTPException(status_code=400, detail=f"unknown run kind {kind!r}")
    mgr = request.app.state.run_manager
    run = mgr.create(kind, body.get("params", {}))
    mgr.start(run, runner)
    return {"run_id": run.id, "status": run.status}


@router.get("")
def list_runs(request: Request) -> dict:
    """All runs with their status and originating agent (for the dashboard)."""
    runs = request.app.state.run_manager.list()
    return {
        "runs": [
            {
                "id": r.id,
                "kind": r.kind,
                "status": r.status,
                "agent_id": r.params.get("agent_id"),
                "error": r.error,
            }
            for r in runs
        ]
    }


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


@router.websocket("/{run_id}/ws")
async def run_ws(websocket: WebSocket, run_id: str) -> None:
    mgr = websocket.app.state.run_manager
    run = mgr.get(run_id)
    if run is None:
        await websocket.close(code=4404)
        return
    await websocket.accept()
    queue = await mgr.subscribe(run)
    try:
        while True:
            frame = await queue.get()
            await websocket.send_json(frame)
            if frame["type"] == "end":
                break
    except WebSocketDisconnect:
        pass
    finally:
        mgr.unsubscribe(run, queue)
