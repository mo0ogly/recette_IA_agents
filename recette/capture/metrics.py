"""Aggregate captured LLM traces into per-agent / per-tool operational metrics.

Pure functions over a list of ``LlmCallTrace``: call counts, error rate, token
totals, latency percentiles, and (when a pricing table is given) cost in USD.
These are OPERATIONAL metrics ABOUT runs -- derived from captured latency/token
values, the same altitude as a run's ``created_at`` -- not a decision-path
input, so they never enter the judge/replay path. Deterministic given the trace
list (nearest-rank percentiles, sorted iteration, no clock, no randomness).
"""

from __future__ import annotations

import math
from collections import defaultdict

from .cost import PricingTable, cost_of
from .llm_trace import LlmCallTrace


def _percentile(sorted_vals: list[int], q: float) -> int:
    """Nearest-rank percentile of an ascending-sorted list (0 when empty)."""
    if not sorted_vals:
        return 0
    rank = max(1, math.ceil(q / 100 * len(sorted_vals)))
    return sorted_vals[min(rank, len(sorted_vals)) - 1]


#: Default error-rate above which a group is flagged "degraded" (R5: a single
#: knob; the router may override from the environment). A trace-derived baseline
#: anomaly signal, in the spirit of the IBM/cogniolab tool-monitoring approach.
DEFAULT_ERROR_THRESHOLD = 0.25


def _group_metrics(
    traces: list[LlmCallTrace],
    pricing: PricingTable | None,
    error_threshold: float,
) -> dict:
    n = len(traces)
    errors = sum(1 for t in traces if t.error)
    error_rate = round(errors / n, 4) if n else 0.0
    total_tokens = sum(t.total_tokens for t in traces)
    latencies = sorted(t.latency_ms for t in traces)
    cost: float | None = None
    if pricing is not None:
        known = [c for c in (cost_of(t, pricing) for t in traces) if c is not None]
        cost = round(sum(known), 6) if known else None
    return {
        "calls": n,
        "errors": errors,
        "error_rate": error_rate,
        "total_tokens": total_tokens,
        "latency_ms": {
            "p50": _percentile(latencies, 50),
            "p95": _percentile(latencies, 95),
            "p99": _percentile(latencies, 99),
        },
        "cost_usd": cost,
        # Anomaly flag: degraded when the error rate exceeds the threshold.
        "health": "degraded" if error_rate > error_threshold else "ok",
    }


def summarize_metrics(
    traces: list[LlmCallTrace],
    pricing: PricingTable | None = None,
    error_threshold: float = DEFAULT_ERROR_THRESHOLD,
) -> dict:
    """Per-agent and per-tool operational metrics over captured traces.

    ``cost_usd`` is ``None`` when no pricing table is supplied or no priced
    model is present (never a guessed zero, see ``cost.py``). Each group carries
    a ``health`` flag (``degraded`` when its error rate exceeds
    ``error_threshold``) -- a trace-derived anomaly signal.
    """
    by_agent: dict[str, list[LlmCallTrace]] = defaultdict(list)
    by_tool: dict[str, list[LlmCallTrace]] = defaultdict(list)
    for t in traces:
        by_agent[t.agent_id].append(t)
        if t.tool_name:
            by_tool[t.tool_name].append(t)
    return {
        "totals": _group_metrics(traces, pricing, error_threshold),
        "agents": {
            a: _group_metrics(ts, pricing, error_threshold) for a, ts in sorted(by_agent.items())
        },
        "tools": {
            t: _group_metrics(ts, pricing, error_threshold) for t, ts in sorted(by_tool.items())
        },
    }
