"""Temporal workflow library: in-memory metrics aggregation (NOT an agent).

True-negative subject of the discovery recette corpus. This is a genuine Temporal
workflow, but it performs no target-system action (no repo/CI/webhook operation):
it only aggregates numbers in memory. The discovery scanner must NOT flag it as an
agent -- this guards against false positives on plain Temporal workloads.
"""

from __future__ import annotations

from datetime import timedelta

from temporalio import activity, workflow


@activity.defn
def aggregate_metrics(values: list[int]) -> int:
    """Sum a batch of metrics (pure in-memory compute, no external side effect)."""
    return sum(values)


@workflow.defn
class MetricsAggregationWorkflow:
    @workflow.run
    async def run(self, batches: list[list[int]]) -> int:
        total = 0
        for batch in batches:
            total += await workflow.execute_activity(
                aggregate_metrics, batch, start_to_close_timeout=timedelta(seconds=10)
            )
        return total
