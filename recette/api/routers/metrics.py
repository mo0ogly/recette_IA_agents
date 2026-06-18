"""Operational metrics over captured LLM traces (GET /metrics/summary).

Aggregates the in-process hook capture (CapturingLlm -> CaptureStore) into
per-agent and per-tool metrics: call counts, error rate, token totals, latency
percentiles, and cost in USD when a pricing table is configured. Read-only,
fail-safe (no capture store -> empty summary). These are operational metrics,
not a decision/judge path -- they never enter replay.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Request

from ...capture.cost import load_pricing_table
from ...capture.metrics import DEFAULT_ERROR_THRESHOLD, summarize_metrics

router = APIRouter(prefix="/metrics", tags=["metrics"])

#: Env override for the error-rate anomaly threshold (R5: config, not a literal).
_THRESHOLD_ENV = "INSPECT_IA_AGENTS_METRICS_ERROR_THRESHOLD"


def _error_threshold() -> float:
    raw = os.environ.get(_THRESHOLD_ENV)
    if raw is None:
        return DEFAULT_ERROR_THRESHOLD
    try:
        return float(raw)
    except ValueError:
        return DEFAULT_ERROR_THRESHOLD


@router.get("/summary")
def metrics_summary(request: Request) -> dict:
    """Per-agent / per-tool operational metrics over all captured traces."""
    store = getattr(request.app.state, "capture_store", None)
    traces = store.all_traces() if store is not None else []
    pricing = load_pricing_table()  # config-driven; {} -> cost stays None
    return summarize_metrics(traces, pricing or None, _error_threshold())
