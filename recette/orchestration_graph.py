"""Interaction graph + graph metrics over a multi-agent orchestration run.

Models a run as a directed graph -- nodes = participants, edges = handoff
transfers (weighted by count) -- and computes graph-theoretic signals
(in/out degree, tool-call volume, weighted PageRank) as observability/risk
indicators over what the team ACTUALLY did. Pure and deterministic (I4): power
iteration with a fixed iteration count over sorted nodes, no clock, no random.

The mechanism is migrated from the AgentMonitor approach (graph attributes over
agent exchanges); the heavy ML "predict-before-execute" regressor is
intentionally NOT taken (would add a non-stdlib dependency, R20).
"""

from __future__ import annotations

from collections import Counter

from .maf_orchestration import OrchestrationRun

_DAMPING = 0.85
_ITERATIONS = 60  # fixed -> deterministic convergence (I4)


def _pagerank(nodes: list[str], edge_weight: Counter[tuple[str, str]]) -> dict[str, float]:
    """Weighted PageRank by power iteration. Dangling nodes (no out-edge)
    redistribute their mass uniformly. Deterministic (fixed iterations, sorted
    nodes). Returns scores summing to ~1."""
    n = len(nodes)
    if n == 0:
        return {}
    out_total: Counter[str] = Counter()
    for (src, _dst), w in edge_weight.items():
        out_total[src] += w
    score = {node: 1.0 / n for node in nodes}
    for _ in range(_ITERATIONS):
        incoming = {node: 0.0 for node in nodes}
        dangling = sum(score[node] for node in nodes if out_total[node] == 0)
        for (src, dst), w in edge_weight.items():
            incoming[dst] += score[src] * (w / out_total[src])
        base = (1.0 - _DAMPING) / n + _DAMPING * dangling / n
        score = {node: base + _DAMPING * incoming[node] for node in nodes}
    return score


def interaction_graph(run: OrchestrationRun) -> dict:
    """The directed interaction graph of ``run`` with per-node graph metrics."""
    nodes = sorted(
        set(run.order)
        | {h.source for h in run.hops}
        | {h.target for h in run.hops}
        | {c.agent_id for c in run.calls}
    )
    edge_weight: Counter[tuple[str, str]] = Counter((h.source, h.target) for h in run.hops)
    out_degree: Counter[str] = Counter()
    in_degree: Counter[str] = Counter()
    for (src, dst), w in edge_weight.items():
        out_degree[src] += w
        in_degree[dst] += w
    tool_calls: Counter[str] = Counter(c.agent_id for c in run.calls)
    pagerank = _pagerank(nodes, edge_weight)
    return {
        "nodes": [
            {
                "id": node,
                "in_degree": in_degree[node],
                "out_degree": out_degree[node],
                "tool_calls": tool_calls[node],
                "pagerank": round(pagerank[node], 4),
            }
            for node in nodes
        ],
        "edges": [
            {"source": src, "target": dst, "weight": w}
            for (src, dst), w in sorted(edge_weight.items())
        ],
    }
