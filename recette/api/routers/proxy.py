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
