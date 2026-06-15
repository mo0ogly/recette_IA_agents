"""Gateway: the single governed entry point for sensitive agent actions (I2).

Flow: resolve agent -> normalize to PlatformActionEvent -> policy decide ->
  allow    -> execute via proxy (I5) -> append action_executed (I1)
  deny     -> append action_denied; proxy NEVER called
  escalate -> append action_requested(pending); NO execution until approval (I6)

Failure modes (failure-modes.md):
- unknown agent / unknown action -> DENY (fail-closed, I3-lite: identity is
  resolved from the config store, cryptographic binding is a documented
  Phase-2 limitation)
- policy evaluation raises -> DENY + platform_error event (never fail-open)
- proxy failure -> auditable failure event, no bypass, no retry-around
- event store failure on the pending/denied path -> the action is not
  executed (an unaudited action must not run)
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .approvals.service import ApprovalService
from .approvals.state_machine import ApprovalAction, InvalidTransition, transition
from .catalog import Catalog
from .catalog.model import RISK_SCORE, RiskLevel
from .events import (
    SCHEMA_VERSION,
    ApprovalState,
    EventKind,
    PlatformActionEvent,
    PolicyDecision,
    PolicyVerdict,
    build_resolution_denied,
)
from .eventstore.protocol import EventStore, StoredEvent
from .ids import EventIdGenerator
from .policy.engine import decide
from .policy.store import PolicyStore
from .proxy.protocol import ExecutionResult, ExternalSystemProxy

if TYPE_CHECKING:
    from .middleware import MiddlewarePipeline


class GatewayError(Exception):
    """Internal gateway failure surfaced to the API layer."""


@dataclass(frozen=True)
class ActionRequest:
    """Raw submission from the API boundary. timestamp is CAPTURED there (I4)."""

    agent_id: str
    action_type: str
    target_system: str
    resource: str
    payload: dict
    timestamp: str  # ISO-8601 UTC, captured at the boundary


@dataclass(frozen=True)
class ActionOutcome:
    event_id: str
    verdict: str
    approval_state: str
    risk_level: str
    policy_version: str | None
    rule_id: str | None
    executed: bool
    result: dict | None
    side_effect_hash: str | None
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "verdict": self.verdict,
            "approval_state": self.approval_state,
            "risk_level": self.risk_level,
            "policy_version": self.policy_version,
            "rule_id": self.rule_id,
            "executed": self.executed,
            "result": self.result,
            "side_effect_hash": self.side_effect_hash,
            "error": self.error,
        }


class AgentResolver:
    """Thin indirection over the ConfigStore so the gateway stays import-light."""

    def __init__(self, get_agent) -> None:  # type: ignore[no-untyped-def]
        self._get_agent = get_agent

    def resolve(self, agent_id: str) -> dict | None:
        agent = self._get_agent(agent_id)
        return agent if isinstance(agent, dict) else None


class Gateway:
    def __init__(
        self,
        *,
        catalog: Catalog,
        policy_store: PolicyStore,
        event_store: EventStore,
        proxy: ExternalSystemProxy,
        id_generator: EventIdGenerator,
        agent_resolver: AgentResolver,
        middleware: MiddlewarePipeline | None = None,
    ) -> None:
        self._catalog = catalog
        self._policies = policy_store
        self._events = event_store
        self._proxy = proxy
        self._ids = id_generator
        self._agents = agent_resolver
        self._approvals = ApprovalService(event_store)
        self._middleware = middleware

    def _after(self, request: ActionRequest, outcome: ActionOutcome) -> ActionOutcome:
        """Run the middleware after-hooks (observe-only) and return the outcome."""
        if self._middleware is not None:
            self._middleware.run_after(request, outcome)
        return outcome

    # --- submission path ---

    def submit(self, request: ActionRequest) -> ActionOutcome:
        event_id = self._ids.next_id()
        agent = self._agents.resolve(request.agent_id)
        if agent is None:
            # Unknown identity: deny, audited (I3 fail-closed).
            event = self._normalize(request, event_id, role="", scope=())
            return self._after(request, self._record_denied(event, reason="unknown agent identity"))

        role = str(agent.get("role", ""))
        scope = tuple(agent.get("capability_scope", ()))
        event = self._normalize(request, event_id, role=role, scope=scope)

        # Middleware before-hook: may DENY (fail-safe), never ALLOW (I2 preserved).
        if self._middleware is not None:
            veto = self._middleware.run_before(request)
            if veto is not None:
                return self._after(request, self._record_denied(event, reason=veto))

        try:
            policy = self._policies.active()
            decision = decide(event, policy, self._catalog)
        except Exception as exc:
            # Policy plane failure -> default DENY, audited (never fail-open).
            self._append(
                EventKind.PLATFORM_ERROR,
                {**event.to_dict(), "error": f"policy evaluation failed: {exc}"},
                event_id=f"{event_id}E",
            )
            return self._after(
                request, self._record_denied(event, reason="policy evaluation failed -> deny")
            )

        recorded = PolicyDecision(
            verdict=decision.verdict,
            policy_version=decision.policy_version,
            rule_id=decision.rule_id,
        )
        event = self._with_decision(event, recorded, decision.risk_level)

        if decision.verdict is PolicyVerdict.DENY:
            return self._after(request, self._record_denied(event, reason=None))
        if decision.verdict is PolicyVerdict.ESCALATE:
            pending = self._with_approval(event, ApprovalState.PENDING)
            self._append(EventKind.ACTION_REQUESTED, pending.to_dict(), event_id=event_id)
            return self._after(
                request,
                ActionOutcome(
                    event_id=event_id,
                    verdict=PolicyVerdict.ESCALATE,
                    approval_state=ApprovalState.PENDING,
                    risk_level=event.risk_level,
                    policy_version=recorded.policy_version,
                    rule_id=recorded.rule_id,
                    executed=False,
                    result=None,
                    side_effect_hash=None,
                ),
            )
        # allow
        return self._after(
            request, self._execute_and_record(event, approval_state=ApprovalState.NONE)
        )

    # --- approval resolution path ---

    def resolve_approval(
        self, *, pending_event_id: str, action: ApprovalAction, approver: str, reason: str | None
    ) -> ActionOutcome:
        stored = self._events.get_by_event_id(pending_event_id)
        if stored is None or stored.kind != EventKind.ACTION_REQUESTED:
            raise GatewayError(f"no pending action event {pending_event_id!r}")
        already = self._approvals.resolved_ids().get(pending_event_id)
        if already is not None:
            raise InvalidTransition(f"action {pending_event_id!r} already resolved to {already!r}")
        new_state = transition(ApprovalState.PENDING, action)

        resolution_id = self._ids.next_id()
        self._append(
            EventKind.APPROVAL_RESOLVED,
            {
                "schema_version": SCHEMA_VERSION,
                "correlates_event_id": pending_event_id,
                "approval_state": new_state,
                "approver": approver,
                "reason": reason,
                "agent_id": stored.payload.get("agent_id"),
                "target_system": stored.payload.get("target_system"),
                "action_type": stored.payload.get("action_type"),
            },
            event_id=resolution_id,
        )

        event = self._event_from_payload(stored.payload)
        if new_state is not ApprovalState.APPROVED:
            # denied or timeout: never executed (I6, never auto-approve).
            return ActionOutcome(
                event_id=pending_event_id,
                verdict=PolicyVerdict.ESCALATE,
                approval_state=new_state,
                risk_level=event.risk_level,
                policy_version=(
                    event.policy_decision.policy_version if event.policy_decision else None
                ),
                rule_id=event.policy_decision.rule_id if event.policy_decision else None,
                executed=False,
                result=None,
                side_effect_hash=None,
            )
        approved = self._with_approval(event, ApprovalState.APPROVED)
        return self._execute_and_record(
            approved, approval_state=ApprovalState.APPROVED, original_event_id=pending_event_id
        )

    def record_resolution_denied(
        self, *, agent_id: str, name: str, reason: str, timestamp: str | None = None
    ) -> ActionOutcome:
        """Audit a CONTAINMENT deny and return a controlled deny outcome (I2/I5).

        Called by the impure run call-site when ``resolve_proxy(..., containment=
        True)`` raised ``ResolutionDenied`` for an undeclared server name: NO proxy
        was built and NO external call was made. This method only APPENDS the
        immutable ``resolution_denied`` event (I1) via the same audit sink and the
        same id generator every other event uses, then returns a deny outcome so
        the run fails safe (no execution). The ``event_id`` is sequence-derived
        (``self._ids``); ``timestamp`` is a captured input, never the host clock
        (I4). The builder is pure -- emission lives here, at the impure boundary.

        The returned ``ActionOutcome`` is provided for symmetry with the other
        submission paths; run call-sites may discard it (the deny is already
        enforced by the raised ``ResolutionDenied`` and the appended event).
        """
        event_id = self._ids.next_id()
        event = build_resolution_denied(
            event_id=event_id,
            agent_id=agent_id,
            name=name,
            reason=reason,
            timestamp=timestamp,
        )
        self._append(EventKind.RESOLUTION_DENIED, event.to_dict(), event_id=event_id)
        return ActionOutcome(
            event_id=event_id,
            verdict=PolicyVerdict.DENY,
            approval_state=ApprovalState.NONE,
            risk_level=str(RiskLevel.HIGH),
            policy_version=None,
            rule_id=None,
            executed=False,
            result=None,
            side_effect_hash=None,
            error=f"resolution denied: {name} ({reason})",
        )

    def sweep_timeouts(self, *, now_iso: str) -> list[str]:
        """Resolve expired pendings to timeout. `now_iso` is a captured input (I4)."""
        policy = self._policies.active()
        expired = self._approvals.expired(
            now_iso=now_iso, timeout_seconds=policy.approval_timeout_seconds
        )
        out = []
        for item in expired:
            self.resolve_approval(
                pending_event_id=item.event_id,
                action=ApprovalAction.TIMEOUT,
                approver="system:timeout-sweep",
                reason=f"approval timeout after {policy.approval_timeout_seconds}s",
            )
            out.append(item.event_id)
        return out

    # --- internals ---

    def _normalize(
        self, request: ActionRequest, event_id: str, *, role: str, scope: tuple[str, ...]
    ) -> PlatformActionEvent:
        spec = self._catalog.get(request.target_system, request.action_type)
        risk_level = spec.risk_level if spec is not None else RiskLevel.CRITICAL
        return PlatformActionEvent(
            event_id=event_id,
            timestamp=request.timestamp,
            agent_id=request.agent_id,
            capability_scope=scope,
            role=role,
            action_type=request.action_type,
            target_system=request.target_system,
            resource=request.resource,
            payload=request.payload,
            risk_score=RISK_SCORE[risk_level],
            risk_level=risk_level,
        )

    @staticmethod
    def _with_decision(
        event: PlatformActionEvent, decision: PolicyDecision, risk_level: RiskLevel
    ) -> PlatformActionEvent:
        return dataclasses.replace(
            event,
            policy_decision=decision,
            risk_level=str(risk_level),
            risk_score=RISK_SCORE[risk_level],
        )

    @staticmethod
    def _with_approval(event: PlatformActionEvent, state: ApprovalState) -> PlatformActionEvent:
        return dataclasses.replace(event, approval_state=str(state))

    @staticmethod
    def _event_from_payload(payload: dict) -> PlatformActionEvent:
        decision_data = payload.get("policy_decision")
        decision = (
            PolicyDecision(
                verdict=decision_data["verdict"],
                policy_version=decision_data["policy_version"],
                rule_id=decision_data.get("rule_id"),
            )
            if isinstance(decision_data, dict)
            else None
        )
        return PlatformActionEvent(
            event_id=str(payload.get("event_id", "")),
            timestamp=str(payload.get("timestamp", "")),
            agent_id=str(payload.get("agent_id", "")),
            capability_scope=tuple(payload.get("capability_scope", ())),
            role=str(payload.get("role", "")),
            action_type=str(payload.get("action_type", "")),
            target_system=str(payload.get("target_system", "")),
            resource=str(payload.get("resource", "")),
            payload=dict(payload.get("payload", {})),
            risk_score=int(payload.get("risk_score", RISK_SCORE[RiskLevel.CRITICAL])),
            risk_level=str(payload.get("risk_level", RiskLevel.CRITICAL)),
            policy_decision=decision,
            approval_state=str(payload.get("approval_state", ApprovalState.NONE)),
            side_effect_hash=payload.get("side_effect_hash"),
            correlates_event_id=payload.get("correlates_event_id"),
            schema_version=str(payload.get("schema_version", SCHEMA_VERSION)),
            extra=dict(payload.get("extra", {})),
        )

    def _record_denied(self, event: PlatformActionEvent, *, reason: str | None) -> ActionOutcome:
        payload = event.to_dict()
        if event.policy_decision is None:
            payload["policy_decision"] = PolicyDecision(
                verdict=PolicyVerdict.DENY, policy_version="", rule_id=None
            ).to_dict()
        if reason is not None:
            payload["extra"] = {**payload.get("extra", {}), "deny_reason": reason}
        self._append(EventKind.ACTION_DENIED, payload, event_id=event.event_id)
        decision = payload["policy_decision"]
        return ActionOutcome(
            event_id=event.event_id,
            verdict=PolicyVerdict.DENY,
            approval_state=ApprovalState.NONE,
            risk_level=event.risk_level,
            policy_version=decision.get("policy_version") or None,
            rule_id=decision.get("rule_id"),
            executed=False,
            result=None,
            side_effect_hash=None,
            error=reason,
        )

    def _execute_and_record(
        self,
        event: PlatformActionEvent,
        *,
        approval_state: ApprovalState,
        original_event_id: str | None = None,
    ) -> ActionOutcome:
        result: ExecutionResult = self._proxy.execute(event)
        decision = event.policy_decision
        if not result.ok:
            # Proxy/external failure: audited failure event, no bypass.
            failure_id = self._ids.next_id()
            self._append(
                EventKind.PLATFORM_ERROR,
                {
                    **event.to_dict(),
                    "approval_state": str(approval_state),
                    "correlates_event_id": original_event_id,
                    "error": result.error or f"proxy failure HTTP {result.status_code}",
                },
                event_id=failure_id,
            )
            return ActionOutcome(
                event_id=original_event_id or event.event_id,
                verdict=str(decision.verdict) if decision else PolicyVerdict.ALLOW,
                approval_state=str(approval_state),
                risk_level=event.risk_level,
                policy_version=decision.policy_version if decision else None,
                rule_id=decision.rule_id if decision else None,
                executed=False,
                result=None,
                side_effect_hash=None,
                error=result.error,
            )
        executed_id = self._ids.next_id() if original_event_id else event.event_id
        payload = {
            **event.to_dict(),
            "event_id": executed_id,
            "approval_state": str(approval_state),
            "side_effect_hash": result.side_effect_hash,
            "correlates_event_id": original_event_id,
        }
        self._append(EventKind.ACTION_EXECUTED, payload, event_id=executed_id)
        return ActionOutcome(
            event_id=original_event_id or executed_id,
            verdict=str(decision.verdict) if decision else PolicyVerdict.ALLOW,
            approval_state=str(approval_state),
            risk_level=event.risk_level,
            policy_version=decision.policy_version if decision else None,
            rule_id=decision.rule_id if decision else None,
            executed=True,
            result=result.response,
            side_effect_hash=result.side_effect_hash,
        )

    def _append(self, kind: EventKind, payload: dict, *, event_id: str) -> StoredEvent:
        return self._events.append(
            event_id=event_id, kind=kind, payload=payload, schema_version=SCHEMA_VERSION
        )
