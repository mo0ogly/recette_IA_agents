"""Side-effect proxy debug endpoints (I5 observability).

Read-only over the in-memory trace ring: the gateway's TracingProxy records each
side effect; this router exposes the recorded traces for the Monaco trace console.
The ring is a jettable view (I1 keeps the durable truth in the append-only audit
log), so a ``clear`` is allowed -- it discards the debug buffer, never the log.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

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
