"""GET /capture/llm-traces -- the in-process hook capture for a run.

Reads back the LlmCallTraces a run's CapturingLlm recorded (intent + tokens +
latency). This is the hook-surface half of the multi-surface view; the eBPF wire
half comes from discoveryprobe. Raw JSON, read-only, fail-safe (unknown run ->
empty list).
"""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(prefix="/capture", tags=["capture"])


@router.get("/llm-traces")
def llm_traces(request: Request, run_id: str = "") -> dict:
    """The captured LLM traces for ``run_id`` (empty when none / unknown)."""
    store = getattr(request.app.state, "capture_store", None)
    traces = store.traces(run_id) if store is not None and run_id else []
    return {"run_id": run_id, "traces": traces, "count": len(traces)}
