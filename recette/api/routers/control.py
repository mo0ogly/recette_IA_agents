"""Control plane summary -- a read-only governance digest over the audit log.

Surfaces the Control plane as a measurable view for the console: how many
actions were allowed / denied / escalated, the approval outcomes (I6), and how
many actions actually executed vs were blocked. It is a pure projection of the
append-only event store (I1: never writes), deterministic (I4: a pure function
of the event list -- no clock, stable counts), so the same log yields the same
summary. The Control plane decides (allow/deny/escalate) and blocks on approval;
this endpoint only COUNTS those decisions, it never makes one.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from ...platform.eventstore.protocol import StoredEvent

router = APIRouter(prefix="/control", tags=["control"])

_VERDICTS = ("allow", "deny", "escalate")
_APPROVALS = ("none", "pending", "approved", "denied", "timeout")


def summarize(events: list[StoredEvent]) -> dict:
    """Aggregate stored events into the Control plane governance digest.

    Pure and deterministic (I4): counts are derived only from the events'
    ``policy_decision.verdict`` / ``approval_state`` / ``kind`` -- no clock, no
    randomness. ``deny_by_default`` is the Control plane's fixed posture, not a
    measured value (failure-modes.md: policy engine down -> default DENY).
    """
    verdicts = {v: 0 for v in _VERDICTS}
    approvals = {a: 0 for a in _APPROVALS}
    total = 0
    executed = 0
    denied_execution = 0
    for event in events:
        payload = event.payload if isinstance(event.payload, dict) else {}
        decision = payload.get("policy_decision")
        if isinstance(decision, dict):
            verdict = decision.get("verdict")
            if verdict in verdicts:
                verdicts[verdict] += 1
                total += 1
        approval = payload.get("approval_state")
        if approval in approvals:
            approvals[approval] += 1
        if event.kind == "action_executed":
            executed += 1
        elif event.kind == "action_denied":
            denied_execution += 1
    return {
        "total": total,
        "verdicts": verdicts,
        "approvals": approvals,
        "executed": executed,
        "denied_execution": denied_execution,
        "deny_by_default": True,
    }


@router.get("/summary")
def control_summary(request: Request) -> dict:
    """The governance digest of the whole audit log (read-only, I1)."""
    store = request.app.state.event_store
    return summarize(store.read_from())
