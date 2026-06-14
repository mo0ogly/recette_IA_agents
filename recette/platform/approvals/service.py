"""ApprovalService: the inbox is a fold over the event log, never a mutable table.

Pending = action_requested events with no approval_resolved event correlating
to them (I1: resolution is a NEW event, the pending event is never updated).
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass

from ..events import EventKind
from ..eventstore.protocol import EventStore


@dataclass(frozen=True)
class PendingApproval:
    event_id: str
    seq: int
    requested_at: str  # captured event timestamp
    agent_id: str
    role: str
    target_system: str
    action_type: str
    resource: str
    risk_level: str
    policy_version: str

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "seq": self.seq,
            "requested_at": self.requested_at,
            "agent_id": self.agent_id,
            "role": self.role,
            "target_system": self.target_system,
            "action_type": self.action_type,
            "resource": self.resource,
            "risk_level": self.risk_level,
            "policy_version": self.policy_version,
        }


def _parse_ts(value: str) -> _dt.datetime:
    return _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


class ApprovalService:
    def __init__(self, store: EventStore) -> None:
        self._store = store

    def resolved_ids(self) -> dict[str, str]:
        """Map of correlates_event_id -> final approval_state."""
        out: dict[str, str] = {}
        for event in self._store.read_from(kind=EventKind.APPROVAL_RESOLVED):
            correlates = event.payload.get("correlates_event_id")
            state = event.payload.get("approval_state")
            if isinstance(correlates, str) and isinstance(state, str):
                out[correlates] = state
        return out

    def pending(self) -> list[PendingApproval]:
        resolved = self.resolved_ids()
        items: list[PendingApproval] = []
        for event in self._store.read_from(kind=EventKind.ACTION_REQUESTED):
            if event.event_id in resolved:
                continue
            p = event.payload
            decision = p.get("policy_decision") or {}
            items.append(
                PendingApproval(
                    event_id=event.event_id,
                    seq=event.seq,
                    requested_at=str(p.get("timestamp", "")),
                    agent_id=str(p.get("agent_id", "")),
                    role=str(p.get("role", "")),
                    target_system=str(p.get("target_system", "")),
                    action_type=str(p.get("action_type", "")),
                    resource=str(p.get("resource", "")),
                    risk_level=str(p.get("risk_level", "")),
                    policy_version=str(decision.get("policy_version", "")),
                )
            )
        return items

    def expired(self, *, now_iso: str, timeout_seconds: int) -> list[PendingApproval]:
        """Pending approvals older than the timeout, relative to a CAPTURED now.

        `now_iso` is an input from the API boundary (I4) -- this module never
        reads the host clock.
        """
        now = _parse_ts(now_iso)
        out = []
        for item in self.pending():
            if not item.requested_at:
                continue
            age = (now - _parse_ts(item.requested_at)).total_seconds()
            if age >= timeout_seconds:
                out.append(item)
        return out
