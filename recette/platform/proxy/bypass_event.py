"""Compensatory ``bypass_detected`` events from a wire<->audit reconciliation.

When ``reconcile`` finds a wire flow with no matching audit event (an unmediated
path -- the ghost-agent signal), the Control Plane records it as a COMPENSATORY
event in the append-only log (I1): a ``PlatformActionEvent`` with
``action_type="bypass_detected"`` and ``policy_decision = deny``. Nothing is
mutated; the bypass is corrected by ADDING an event (canonical-event-model).

Because it is a normal canonical event, replaying the stream reproduces it
byte-for-byte (I4): this is the scenario's step 6. The builder is pure -- the
``event_id`` and the captured ``timestamp`` are INPUTS (never read from the host
clock inside the decision path), exactly like the gateway's normalization.

The ghost has no bound identity (I3 negative): ``agent_id`` is the
``unregistered`` sentinel and ``capability_scope`` is empty.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from ..events import PlatformActionEvent, PolicyDecision, PolicyVerdict
from .protocol import side_effect_hash
from .reconcile import ReconcileReport, target_of

UNREGISTERED_AGENT = "unregistered"
_POLICY_VERSION = "reconcile/1"
_RULE_ID = "unmediated-path"


def bypass_flow_hash(flow: dict) -> str:
    """Stable identity of an unmediated flow (target + path + response). Used to
    dedup repeated detections of the SAME bypass across polls (idempotent raise)."""
    return side_effect_hash(
        target_of(flow),
        "bypass_detected",
        str(flow.get("path", "")),
        {"response_body": flow.get("response_body", "")},
    )


def build_bypass_event(flow: dict, *, event_id: str, timestamp: str) -> PlatformActionEvent:
    """Build the compensatory ``bypass_detected`` event for one unmediated flow.

    Pure and deterministic: same ``(flow, event_id, timestamp)`` -> same event,
    byte for byte (I4). ``target_system`` is the wire target (host:port), the
    evidence flow is the payload, the verdict is a hard deny.
    """
    return PlatformActionEvent(
        event_id=event_id,
        timestamp=timestamp,
        agent_id=UNREGISTERED_AGENT,
        capability_scope=(),
        role="unknown",
        action_type="bypass_detected",
        target_system=target_of(flow),
        resource=str(flow.get("path", "")),
        payload=dict(flow),
        risk_score=3,
        risk_level="high",
        policy_decision=PolicyDecision(
            verdict=PolicyVerdict.DENY, policy_version=_POLICY_VERSION, rule_id=_RULE_ID
        ),
        side_effect_hash=bypass_flow_hash(flow),
    )


def raise_bypass_events(
    report: ReconcileReport,
    *,
    next_event_id: Callable[[], str],
    timestamp: str,
    already_raised: Iterable[str] = (),
) -> list[PlatformActionEvent]:
    """Build one ``bypass_detected`` event per NEW unmediated flow (seq order).

    Idempotent: a flow whose ``side_effect_hash`` is in ``already_raised`` is
    skipped, so re-running over the same buffer does not append duplicates
    (I1 stays append-only; we just do not spam). ``next_event_id`` is pulled
    only for an event that is actually emitted, keeping id allocation stable.
    The caller appends the returned events to the store with kind
    ``EventKind.BYPASS_DETECTED``.
    """
    seen = set(already_raised)
    events: list[PlatformActionEvent] = []
    for flow in report.bypass_flows:  # reconcile already orders these by seq (I4)
        digest = bypass_flow_hash(flow)
        if digest in seen:
            continue
        seen.add(digest)
        events.append(build_bypass_event(flow, event_id=next_event_id(), timestamp=timestamp))
    return events
