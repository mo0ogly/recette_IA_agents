"""U1: run launch/inspect/stop endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect

from .._timestamp import capture_timestamp
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
        # Fail fast on an incomplete agent: the lane_b runner reads these as
        # required fields, so a missing one must surface as an explicit 400
        # here, never as a cryptic KeyError 500 inside the run thread.
        # principal/target_system/goal must be non-empty; capability_scope may
        # legitimately be an empty list (an unprivileged agent), so it only has
        # to be present, not truthy.
        missing = [f for f in ("principal", "target_system", "goal") if not agent_cfg.get(f)]
        if agent_cfg.get("capability_scope") is None:
            missing.append("capability_scope")
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"agent {agent_cfg['id']!r} missing required field(s): {missing}",
            )
        # Passport admission gate (Control Plane, I2/I3). `now` is captured here at
        # the boundary (I4 INPUT); the decision is a pure function of the passport,
        # the declared scope, the trust keyring and `now`. The verdict is ALWAYS
        # audited (I1) BEFORE any enforce-mode 403, so the denial itself is on the
        # log. Fail-safe: a non-trusted agent is denied only in enforce mode.
        from ...platform.admission import admit_agent, load_agent_passport
        from ...platform.events import SCHEMA_VERSION, EventKind

        now = capture_timestamp()
        passport = load_agent_passport(agent_cfg["id"], request.app.state.passport_dir)
        verdict = admit_agent(
            passport,
            agent_cfg.get("capability_scope"),
            request.app.state.passport_trust,
            now,
            request.app.state.passport_enforce,
        )
        request.app.state.event_store.append(
            event_id=request.app.state.admission_ids.next_id(),
            kind=EventKind.AGENT_ADMISSION,
            payload={
                "agent_id": agent_cfg["id"],
                "status": verdict.status,
                "reasons": list(verdict.reasons),
                "mode": verdict.mode,
                "admitted": verdict.admitted,
            },
            schema_version=SCHEMA_VERSION,
        )
        if request.app.state.passport_enforce and verdict.status != "trusted":
            raise HTTPException(
                status_code=403,
                detail=(
                    f"agent {agent_cfg['id']!r} admission denied: "
                    f"{verdict.status} {list(verdict.reasons)}"
                ),
            )
        from ...llm import LlmBackend
        from ..runners import build_stub_llm, make_lane_b_runner

        llm: LlmBackend
        if "stub_script" in params:
            llm = build_stub_llm(params["stub_script"])
        elif agent_cfg.get("ai_mode", "mock") != "real" and agent_cfg.get("scenario"):
            # A mock agent carries its decisions in its scenario; derive the stub
            # from it so the proxy launcher (which sends only agent_id) can run a
            # key-less mock agent, mirroring the campaign runner.
            llm = build_stub_llm(agent_cfg["scenario"])
        else:
            backend_id = agent_cfg.get("ai_backend_id")
            if not backend_id:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"agent {agent_cfg['id']!r} has no ai_backend_id "
                        "(required without stub_script)"
                    ),
                )
            backend = store.get_ai_backend(backend_id)
            if backend is None:
                raise HTTPException(status_code=400, detail="unknown ai_backend_id")
            from ...llm import build_llm

            # Per-backend secret first, then env fallback (R8). base_url only
            # matters for openai_compat. The key is never logged.
            api_key = request.app.state.secret_store.get_secret(backend_id)
            llm = build_llm(
                backend["provider"],
                backend["model"],
                base_url=backend.get("base_url"),
                api_key=api_key,
            )
        mgr = request.app.state.run_manager
        run = mgr.create("lane_b", params)
        # config_store carries the server registry for per-agent proxy routing (I5).
        # The shared trace recorder makes a real agent's side effects show up in
        # the proxy debug console (parametrable via INSPECT_IA_AGENTS_PROXY_DEBUG, R5).
        mgr.start(
            run,
            make_lane_b_runner(
                agent_cfg,
                llm,
                config_store=store,
                recorder=request.app.state.proxy_trace_recorder,
                debug_enabled=request.app.state.proxy_debug_enabled,
                run_id=run.id,
                gateway=request.app.state.gateway,
                # Active transport route selected in the network-debug consoles
                # (direct vs wire overlay). Transport only -- not the decision (I4).
                wire_proxy_url=request.app.state.proxy_route_registry.active_proxy_url(),
            ),
        )
        return {
            "run_id": run.id,
            "status": run.status,
            "admission": {
                "status": verdict.status,
                "mode": verdict.mode,
                "admitted": verdict.admitted,
            },
        }
    if kind == "lane_b_process":
        # Run the agent as a SEPARATE OS process (eBPF-observable). Mock-only:
        # the process path runs the deterministic StubLlm loop, never a live
        # provider (a live key never crosses a subprocess boundary here).
        from ..runners import make_process_run_runner

        store = request.app.state.config_store
        agent_cfg = store.get_agent(str(body.get("params", {}).get("agent_id", "")))
        if agent_cfg is None:
            raise HTTPException(status_code=400, detail="unknown lane_b_process agent_id")
        if agent_cfg.get("ai_mode", "mock") == "real":
            raise HTTPException(status_code=400, detail="process mode is mock-only")
        if not agent_cfg.get("scenario"):
            raise HTTPException(status_code=400, detail="process mode needs a mock scenario")
        mgr = request.app.state.run_manager
        run = mgr.create("lane_b_process", body.get("params", {}))
        # Pass the servers registry so a server-bound agent runs through the real
        # ProxyForge (real TCP connects -> the eBPF connect surface).
        mgr.start(run, make_process_run_runner(agent_cfg, store.list_servers()))
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
                "created_at": r.created_at,
                "agent_id": r.params.get("agent_id"),
                "campaign_id": r.params.get("campaign_id"),
                "error": r.error,
            }
            for r in runs
        ]
    }


@router.delete("")
def purge_runs(request: Request, agent_id: str | None = None) -> dict:
    """Purge finished runs from the ephemeral run read-model (optionally for a
    single agent). Active runs (pending/running) are preserved. This NEVER
    mutates the append-only audit event store (I1); it only clears in-memory
    run records."""
    removed = request.app.state.run_manager.clear(agent_id=agent_id)
    return {"removed": removed}


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


@router.get("/{run_id}/verdict")
def get_verdict(request: Request, run_id: str) -> dict:
    """F1 -- judge this run's real action log against the agent's declared
    manifest, on the 4 recette dimensions. Read-model only: computed on demand,
    never written to the event store (I1); deterministic (I4)."""
    run = request.app.state.run_manager.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="no such run")
    agent_id = run.params.get("agent_id")
    if not agent_id:
        raise HTTPException(status_code=400, detail="run has no agent_id to judge")
    agent_cfg = request.app.state.config_store.get_agent(agent_id)
    if agent_cfg is None:
        raise HTTPException(status_code=404, detail="unknown agent for this run")
    from ..verdict import action_log_from_run_events, judge_run, verdict_payload

    action_log = action_log_from_run_events(list(run.events))
    result = judge_run(agent_cfg, action_log)
    return {
        "run_id": run.id,
        "agent_id": agent_id,
        "action_count": len(action_log),
        **verdict_payload(result),
    }


@router.post("/{run_id}/submit-verdict", status_code=201)
def submit_run_verdict(request: Request, run_id: str) -> dict:
    """Close the recette loop: judge this run's real action log (F1) and submit
    the result to the Verdicts board exactly as an external identification tool
    would (POST /verdicts). The submitted result is judged against the agent's
    stored ground_truth, so an agent without ground truth yields SKIP, never a
    vacuous PASS. Deterministic (judge_run is pure, I4); append-only (I1)."""
    run = request.app.state.run_manager.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="no such run")
    agent_id = run.params.get("agent_id")
    if not agent_id:
        raise HTTPException(status_code=400, detail="run has no agent_id to judge")
    agent_cfg = request.app.state.config_store.get_agent(agent_id)
    if agent_cfg is None:
        raise HTTPException(status_code=404, detail="unknown agent for this run")
    from ..verdict import action_log_from_run_events, judge_run, verdict_payload
    from .verdicts import judge_and_store

    action_log = action_log_from_run_events(list(run.events))
    payload = verdict_payload(judge_run(agent_cfg, action_log))
    # Shape the run verdict as a /verdicts result entry. The run was actually
    # executed, so the agent is observed as detected; identity is the declared
    # principal (matched against ground_truth.expected_identity).
    result = {
        "agent_id": agent_id,
        "detected": True,
        "identity": agent_cfg.get("principal", ""),
        "verdict": payload["verdict"],
        "dimensions": payload["dimensions"],
    }
    stored = judge_and_store(request, f"run:{run_id}", [result])
    return {"run_id": run_id, "agent_id": agent_id, **stored}


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
