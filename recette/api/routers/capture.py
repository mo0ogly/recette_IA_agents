"""GET /capture/llm-traces -- the in-process hook capture for a run.

Reads back the LlmCallTraces a run's CapturingLlm recorded (intent + tokens +
latency). This is the hook-surface half of the multi-surface view; the eBPF wire
half comes from discoveryprobe. Raw JSON, read-only, fail-safe (unknown run ->
empty list).
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from ...capture.cost import load_pricing_table
from ...otel import capture_spans, to_otlp

router = APIRouter(prefix="/capture", tags=["capture"])


@router.get("/llm-traces")
def llm_traces(request: Request, run_id: str = "") -> dict:
    """The captured LLM traces for ``run_id`` (empty when none / unknown)."""
    store = getattr(request.app.state, "capture_store", None)
    traces = store.traces(run_id) if store is not None and run_id else []
    return {"run_id": run_id, "traces": traces, "count": len(traces)}


@router.get("/otlp")
def capture_otlp(request: Request, run_id: str = "") -> dict:
    """Token-rich OTLP/JSON GenAI spans for a run's captured traces.

    Emits ``gen_ai.usage.*`` tokens + cost on each execute_tool span (sourced
    from the capture surface, which carries the counts) -- interoperable with
    any OTel backend. Read-only, fail-safe (unknown run -> empty document)."""
    store = getattr(request.app.state, "capture_store", None)
    if store is None or not run_id:
        return to_otlp([])
    pricing = load_pricing_table()
    dicts = [t.to_dict(pricing or None) for t in store.run_traces(run_id)]
    seed = str(dicts[0]["agent_id"]) if dicts else run_id
    return to_otlp(capture_spans(dicts, seed))
