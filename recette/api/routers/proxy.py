"""Side-effect proxy debug endpoints (I5 observability).

Two altitudes over the SAME side effects:
- ``/proxy/traces`` -- the APPLICATION view (ProxyTrace), recorded by the
  gateway's TracingProxy at the ExternalSystemProxy boundary.
- ``/proxy/wire`` -- the NETWORK view (WireFlow), the bytes on the wire, fed by
  the OPTIONAL mitmproxy Docker overlay (``POST /proxy/wire`` ingest).

Both rings are jettable views (I1 keeps the durable truth in the append-only
audit log), so a ``clear`` is allowed -- it discards the debug buffer, never the
log. The ingest is the only mutating route here and it only appends to a bounded
in-memory ring; it never touches the event store.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/proxy", tags=["proxy"])


@router.get("/debug")
def get_debug_status(request: Request) -> dict:
    """Whether proxy debug tracing is on, and how many traces are buffered."""
    recorder = request.app.state.proxy_trace_recorder
    return {
        "debug_enabled": bool(request.app.state.proxy_debug_enabled),
        "trace_count": len(recorder.snapshot()),
    }


@router.get("/traces")
def list_traces(request: Request, tail: int | None = None, run_id: str | None = None) -> dict:
    """Recorded side-effect traces in monotone seq order (oldest first).

    ``run_id`` narrows the view to the traces of one run (F3 run <-> traces
    link); applied before ``tail``. ``tail`` keeps only the last N traces
    (live-console backfill). Stays read-only.
    """
    traces = request.app.state.proxy_trace_recorder.snapshot()
    if run_id is not None:
        traces = [t for t in traces if t.run_id == run_id]
    if tail is not None and tail >= 0:
        traces = traces[-tail:]
    return {
        "debug_enabled": bool(request.app.state.proxy_debug_enabled),
        "traces": [t.to_dict() for t in traces],
    }


@router.delete("/traces")
def clear_traces(request: Request) -> dict:
    """Discard the debug trace buffer (the audit log is untouched, I1)."""
    request.app.state.proxy_trace_recorder.clear()
    return {"cleared": True}


@router.get("/wire/status")
def get_wire_status(request: Request) -> dict:
    """Whether the wire overlay is active, its proxy URL, and buffered flow count.

    ``enabled`` reflects configuration (INSPECT_IA_AGENTS_WIRE_PROXY set): it says the
    overlay is wired, not that a container is currently reachable -- liveness is
    observed through arriving flows, not asserted here (fail-safe, no probe in a
    read path)."""
    proxy_url = request.app.state.wire_proxy_url
    recorder = request.app.state.wire_flow_recorder
    return {
        "enabled": proxy_url is not None,
        "proxy_url": proxy_url,
        "flow_count": len(recorder.snapshot()),
    }


@router.post("/wire", status_code=201)
def ingest_wire_flow(request: Request, payload: dict) -> dict:
    """Ingest one normalized flow from the mitmproxy overlay addon.

    Appends to the bounded wire ring only; never the audit log. A non-object
    payload is a malformed ingest -> 422 (the addon controls the shape, but the
    body crosses a process boundary, so it is validated, not trusted)."""
    try:
        flow = request.app.state.wire_flow_recorder.record(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"recorded": True, "seq": flow.seq}


@router.get("/wire")
def list_wire_flows(request: Request, tail: int | None = None, run_id: str | None = None) -> dict:
    """Recorded wire flows in monotone seq order (oldest first).

    ``run_id`` narrows to one run's flows (applied before ``tail``); ``tail``
    keeps only the last N. Read-only."""
    flows = request.app.state.wire_flow_recorder.snapshot()
    if run_id is not None:
        flows = [f for f in flows if f.run_id == run_id]
    if tail is not None and tail >= 0:
        flows = flows[-tail:]
    return {
        "enabled": request.app.state.wire_proxy_url is not None,
        "proxy_url": request.app.state.wire_proxy_url,
        "flows": [f.to_dict() for f in flows],
    }


@router.delete("/wire")
def clear_wire_flows(request: Request) -> dict:
    """Discard the wire flow buffer (the audit log is untouched, I1)."""
    request.app.state.wire_flow_recorder.clear()
    return {"cleared": True}


@router.get("/route")
def get_proxy_route(request: Request) -> dict:
    """The selectable transport targets (direct vs wire overlay) + the active one.

    Transport selection only -- it changes how a side effect reaches the target,
    never the decision (I4). Surfaced in the network-debug consoles."""
    registry = request.app.state.proxy_route_registry
    return {
        "active": registry.active(),
        "targets": [t.to_dict() for t in registry.targets()],
    }


@router.post("/route")
def set_proxy_route(request: Request, body: dict) -> dict:
    """Select the active transport target. Applies to runs started afterwards.

    A missing/unknown target is a 422 (fail-safe: never silently keep the old
    route on a bad selection)."""
    target = body.get("target")
    if not isinstance(target, str) or not target:
        raise HTTPException(status_code=422, detail="body.target (string) is required")
    try:
        chosen = request.app.state.proxy_route_registry.set_active(target)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"active": chosen.id, "proxy_url": chosen.proxy_url}


def _reconcile_report(request: Request, run_id: str | None, *, strict: bool = False):
    """Compute the run-scoped wire<->audit reconciliation over the live recorders.

    Shared by the read endpoint and the raise endpoint so both see the exact
    same join. ``strict`` selects the phase-3 per-flow side_effect_hash join
    (catches a ghost via an allowlisted target); the default is the phase-2
    target/run join. Pure given the recorder snapshots (I4); no side effect."""
    from urllib.parse import urlparse

    from ...platform.proxy.lab_proxy import lab_url_from_env
    from ...platform.proxy.reconcile import (
        build_allowlist,
        reconcile_run,
        reconcile_strict,
        target_of,
    )

    flows = request.app.state.wire_flow_recorder.snapshot()
    traces = request.app.state.proxy_trace_recorder.snapshot()
    if run_id is not None:
        flows = [f for f in flows if f.run_id == run_id]
        traces = [t for t in traces if t.run_id == run_id]
    lab = urlparse(lab_url_from_env())
    # Normalize through target_of so "localhost:8082" matches a flow recorded as
    # "127.0.0.1:8082" (and vice versa).
    lab_host = target_of({"host": lab.hostname or "127.0.0.1", "port": lab.port or 8082})
    allow = build_allowlist(
        servers=request.app.state.config_store.list_servers(),
        lab_host=lab_host,
        llm_hosts=set(),
    )
    join = reconcile_strict if strict else reconcile_run
    return join([f.to_dict() for f in flows], [t.to_dict() for t in traces], allow)


@router.get("/reconcile")
def get_reconcile(request: Request, run_id: str | None = None, strict: bool = False) -> dict:
    """Wire-vs-audit reconciliation (run-scoped join).

    Joins the wire view (WireFlow) with the audit view (ProxyTrace) by run_id.
    A wire flow whose target (host:port) is a mediated endpoint (the lab, a
    mock_local server) is EXPLAINED; a flow to a non-mediated target (e.g. the
    shadow-db honeypot :9113) has no matching audit event -- the ghost-agent
    signal. ``audited_run_ids`` reports which runs produced a genuine mediated
    side effect. With ``strict=true`` (phase 3) every governed-action flow to a
    mediated target must also carry a matching ``side_effect_hash``, so a ghost
    hitting an allowlisted server directly is caught too (``bypass_reason``
    distinguishes ``non_mediated_target`` from ``no_audit_event``). The lab
    OBSERVES the unmediated path; it does not ENFORCE a network block. Read-only;
    POST /proxy/reconcile/raise records the bypass as a compensatory event."""
    report = _reconcile_report(request, run_id, strict=strict)
    return {"run_id": run_id, "strict": strict, **report.to_dict()}


@router.post("/reconcile/raise")
def raise_reconcile(request: Request, run_id: str | None = None, strict: bool = False) -> dict:
    """Record each detected bypass as a compensatory ``bypass_detected`` event
    in the append-only audit log (I1) -- the Control Plane alert (scenario step 5).

    Idempotent: a bypass already recorded (same side_effect_hash) is not appended
    twice, so polling the raise endpoint never spams the log. The decision
    (reconcile) is pure; the event ``timestamp`` is a wall-clock value captured
    HERE at the boundary as an INPUT (I4), never read inside the join. Because
    the result is a normal canonical event, replaying the stream reproduces it
    (step 6)."""
    from datetime import UTC, datetime

    from ...platform.events import EventKind
    from ...platform.proxy.bypass_event import raise_bypass_events
    from ..app import RestartSafeIdGenerator

    store = request.app.state.event_store
    report = _reconcile_report(request, run_id, strict=strict)
    already = {
        e.payload.get("side_effect_hash")
        for e in store.read_from(kind=EventKind.BYPASS_DETECTED)
        if e.payload.get("side_effect_hash")
    }
    ids = RestartSafeIdGenerator(store)
    timestamp = datetime.now(UTC).isoformat()
    events = raise_bypass_events(
        report, next_event_id=ids.next_id, timestamp=timestamp, already_raised=already
    )
    for event in events:
        store.append(
            event_id=event.event_id,
            kind=EventKind.BYPASS_DETECTED,
            payload=event.to_dict(),
            schema_version=event.schema_version,
        )
    return {"raised": len(events), "event_ids": [e.event_id for e in events]}
