"""Canonical platform event model (schema_version 2.0).

Full AgentActionEvent per .claude/rules/canonical-event-model.md, extended
with documented v2 fields: kind (event-store record type), risk_level and
correlates_event_id (approval resolution linkage). The legacy recette corpus
model in recette/events.py is untouched; this module is the platform-side
contract.

Determinism (I4): timestamp is an INPUT captured at the boundary, never read
from the host clock inside the decision path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

SCHEMA_VERSION = "2.0"


class EventKind(StrEnum):
    """Record types appended to the event store. Corrections are new events (I1)."""

    ACTION_REQUESTED = "action_requested"  # escalate -> pending approval (I6)
    ACTION_EXECUTED = "action_executed"  # allow/approved -> executed via proxy (I5)
    ACTION_DENIED = "action_denied"  # deny verdict, never executed
    APPROVAL_RESOLVED = "approval_resolved"  # approved | denied | timeout
    PLATFORM_ERROR = "platform_error"  # audited internal failure (fail-safe deny)
    BYPASS_DETECTED = "bypass_detected"  # unmediated path observed post-hoc (wire<->audit)
    RESOLUTION_DENIED = "resolution_denied"  # private-DNS name not in allowlist (containment)


class PolicyVerdict(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    ESCALATE = "escalate"


class ApprovalState(StrEnum):
    NONE = "none"
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    TIMEOUT = "timeout"


@dataclass(frozen=True)
class PolicyDecision:
    """Decision payload recorded with the event -- carries the policy version (I4)."""

    verdict: str  # PolicyVerdict value
    policy_version: str
    rule_id: str | None  # None => default-deny fired

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "policy_version": self.policy_version,
            "rule_id": self.rule_id,
        }


@dataclass(frozen=True)
class PlatformActionEvent:
    """One normalized agent action flowing through the governed path."""

    event_id: str
    timestamp: str  # captured input, ISO-8601 UTC (I4)
    agent_id: str
    capability_scope: tuple[str, ...]
    role: str
    action_type: str
    target_system: str
    resource: str
    payload: dict
    risk_score: int  # deterministic integer mapping (low=1 .. critical=4)
    risk_level: str
    policy_decision: PolicyDecision | None = None
    approval_state: str = ApprovalState.NONE
    side_effect_hash: str | None = None
    correlates_event_id: str | None = None
    schema_version: str = SCHEMA_VERSION
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "agent_id": self.agent_id,
            "capability_scope": list(self.capability_scope),
            "role": self.role,
            "action_type": self.action_type,
            "target_system": self.target_system,
            "resource": self.resource,
            "payload": self.payload,
            "risk_score": self.risk_score,
            "risk_level": self.risk_level,
            "policy_decision": (
                self.policy_decision.to_dict() if self.policy_decision is not None else None
            ),
            "approval_state": self.approval_state,
            "side_effect_hash": self.side_effect_hash,
            "correlates_event_id": self.correlates_event_id,
            "extra": self.extra,
        }


@dataclass(frozen=True)
class ResolutionDeniedEvent:
    """A private-DNS name an agent tried to resolve was denied by containment.

    First-class AUDITED signal (I1): the denied ``name`` is not in the agent's
    declared allowlist, so the resolver refuses it and records this immutable
    event. Frozen -- corrections are new events, never mutations.
    """

    agent_id: str
    name: str  # the denied name
    reason: str
    kind: str = EventKind.RESOLUTION_DENIED
    timestamp: str | None = None  # captured input, never read from the host clock (I4)
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "timestamp": self.timestamp,
            "agent_id": self.agent_id,
            "name": self.name,
            "reason": self.reason,
        }


def build_resolution_denied(
    *,
    agent_id: str,
    name: str,
    reason: str,
    timestamp: str | None = None,
) -> ResolutionDeniedEvent:
    """Build the audited ``resolution_denied`` containment event.

    Pure and deterministic: same ``(agent_id, name, reason, timestamp)`` -> same
    event, byte for byte (I4). ``timestamp`` is an INJECTED input (default
    ``None``); the builder never reads the host clock.
    """
    return ResolutionDeniedEvent(
        agent_id=agent_id,
        name=name,
        reason=reason,
        timestamp=timestamp,
    )
