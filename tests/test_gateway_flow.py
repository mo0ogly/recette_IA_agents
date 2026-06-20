"""Gateway invariants: I2 single path, I5 proxy-only side effects, I6 blocking approval."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from recette.platform.approvals.state_machine import ApprovalAction, InvalidTransition
from recette.platform.catalog import Catalog
from recette.platform.catalog.model import ActionSpec, Criticality, RiskLevel
from recette.platform.events import ApprovalState, EventKind, PolicyVerdict
from recette.platform.eventstore.memory_store import InMemoryEventStore
from recette.platform.gateway import ActionRequest, AgentResolver, Gateway
from recette.platform.ids import SequenceIdGenerator
from recette.platform.policy.model import PolicyVersion, baseline_from_catalog
from recette.platform.policy.store import PolicyStore
from recette.platform.proxy.protocol import ExecutionResult, side_effect_hash

SPECS = (
    ActionSpec(
        target_system="okta",
        action_type="suspend_user",
        risk_level=RiskLevel.HIGH,
        criticality=Criticality.C2,
        verdict_privileged=PolicyVerdict.ESCALATE,
        verdict_default=PolicyVerdict.DENY,
        privileged_roles=("identity_admin",),
        description="Suspend an Okta user",
    ),
    ActionSpec(
        target_system="okta",
        action_type="list_users",
        risk_level=RiskLevel.LOW,
        criticality=Criticality.C4,
        verdict_privileged=PolicyVerdict.ALLOW,
        verdict_default=PolicyVerdict.DENY,
        privileged_roles=("identity_admin",),
        description="List users (read-only)",
    ),
    ActionSpec(
        target_system="data_platform",
        action_type="delete_logs",
        risk_level=RiskLevel.CRITICAL,
        criticality=Criticality.C1,
        verdict_privileged=PolicyVerdict.DENY,
        verdict_default=PolicyVerdict.DENY,
        privileged_roles=(),
        description="Delete logs (never allowed)",
    ),
)

AGENTS = {
    "agent-admin": {"id": "agent-admin", "role": "identity_admin", "capability_scope": ["okta"]},
    "agent-bot": {"id": "agent-bot", "role": "marketing_bot", "capability_scope": []},
}


class RecordingProxy:
    """Stub proxy that records calls; deterministic responses."""

    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[str] = []
        self.fail = fail

    def execute(self, event) -> ExecutionResult:  # type: ignore[no-untyped-def]
        self.calls.append(f"{event.target_system}/{event.action_type}")
        if self.fail:
            return ExecutionResult(ok=False, status_code=0, error="proxy down")
        response = {"done": True}
        return ExecutionResult(
            ok=True,
            status_code=200,
            response=response,
            side_effect_hash=side_effect_hash(
                event.target_system, event.action_type, event.resource, response
            ),
        )


def _request(agent_id: str, target: str, action: str) -> ActionRequest:
    return ActionRequest(
        agent_id=agent_id,
        action_type=action,
        target_system=target,
        resource="org/acme",
        payload={"reason": "test"},
        timestamp="2026-06-12T10:00:00Z",
    )


class TestGatewayFlow(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.catalog = Catalog(SPECS)
        self.policy_store = PolicyStore(Path(self._tmp.name))
        self.policy_store.publish(baseline_from_catalog(self.catalog, version="v-test"))
        self.events = InMemoryEventStore()
        self.proxy = RecordingProxy()
        self.gateway = Gateway(
            catalog=self.catalog,
            policy_store=self.policy_store,
            event_store=self.events,
            proxy=self.proxy,
            id_generator=SequenceIdGenerator(),
            agent_resolver=AgentResolver(lambda agent_id: AGENTS.get(agent_id)),
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_allow_executes_and_records_side_effect_hash(self) -> None:
        outcome = self.gateway.submit(_request("agent-admin", "okta", "list_users"))
        self.assertEqual(outcome.verdict, PolicyVerdict.ALLOW)
        self.assertTrue(outcome.executed)
        self.assertIsNotNone(outcome.side_effect_hash)
        executed = self.events.read_from(kind=EventKind.ACTION_EXECUTED)
        self.assertEqual(len(executed), 1)
        self.assertEqual(executed[0].payload["side_effect_hash"], outcome.side_effect_hash)

    def test_deny_never_calls_proxy(self) -> None:
        outcome = self.gateway.submit(_request("agent-bot", "okta", "suspend_user"))
        self.assertEqual(outcome.verdict, PolicyVerdict.DENY)
        self.assertFalse(outcome.executed)
        self.assertEqual(self.proxy.calls, [])
        self.assertEqual(len(self.events.read_from(kind=EventKind.ACTION_DENIED)), 1)

    def test_policy_engine_crash_denies_and_audits_platform_error(self) -> None:
        """Failure-modes: a policy-plane exception -> DENY, audited, never fail-open (I2).

        A normally-ALLOWED action (agent-admin okta list_users) must be refused
        when the policy plane raises, and the failure must leave an auditable
        PLATFORM_ERROR plus a reasoned ACTION_DENIED -- no optimistic execution.
        """

        def boom() -> PolicyVersion:
            raise RuntimeError("corrupted policy")

        self.policy_store.active = boom  # type: ignore[method-assign]
        outcome = self.gateway.submit(_request("agent-admin", "okta", "list_users"))

        self.assertEqual(outcome.verdict, PolicyVerdict.DENY)
        self.assertFalse(outcome.executed)
        self.assertEqual(self.proxy.calls, [])  # fail-closed: proxy never reached
        errors = self.events.read_from(kind=EventKind.PLATFORM_ERROR)
        self.assertEqual(len(errors), 1)
        self.assertIn("policy evaluation failed", errors[0].payload["error"])
        denied = self.events.read_from(kind=EventKind.ACTION_DENIED)
        self.assertEqual(len(denied), 1)
        self.assertEqual(
            denied[0].payload["extra"]["deny_reason"], "policy evaluation failed -> deny"
        )

    def test_escalate_blocks_until_approval(self) -> None:
        outcome = self.gateway.submit(_request("agent-admin", "okta", "suspend_user"))
        self.assertEqual(outcome.verdict, PolicyVerdict.ESCALATE)
        self.assertEqual(outcome.approval_state, ApprovalState.PENDING)
        self.assertFalse(outcome.executed)
        self.assertEqual(self.proxy.calls, [])  # I6: nothing executed while pending

        resolved = self.gateway.resolve_approval(
            pending_event_id=outcome.event_id,
            action=ApprovalAction.APPROVE,
            approver="user:rssi",
            reason="ticket-42",
        )
        self.assertTrue(resolved.executed)
        self.assertEqual(self.proxy.calls, ["okta/suspend_user"])
        self.assertIsNotNone(resolved.side_effect_hash)

    def test_denied_approval_never_executes(self) -> None:
        outcome = self.gateway.submit(_request("agent-admin", "okta", "suspend_user"))
        resolved = self.gateway.resolve_approval(
            pending_event_id=outcome.event_id,
            action=ApprovalAction.DENY,
            approver="user:rssi",
            reason="no",
        )
        self.assertFalse(resolved.executed)
        self.assertEqual(resolved.approval_state, ApprovalState.DENIED)
        self.assertEqual(self.proxy.calls, [])

    def test_double_resolution_rejected(self) -> None:
        outcome = self.gateway.submit(_request("agent-admin", "okta", "suspend_user"))
        self.gateway.resolve_approval(
            pending_event_id=outcome.event_id,
            action=ApprovalAction.DENY,
            approver="u",
            reason=None,
        )
        with self.assertRaises(InvalidTransition):
            self.gateway.resolve_approval(
                pending_event_id=outcome.event_id,
                action=ApprovalAction.APPROVE,
                approver="u",
                reason=None,
            )

    def test_unknown_agent_denied(self) -> None:
        outcome = self.gateway.submit(_request("ghost", "okta", "list_users"))
        self.assertEqual(outcome.verdict, PolicyVerdict.DENY)
        self.assertEqual(self.proxy.calls, [])

    def test_pure_deny_action_denied_for_privileged_role(self) -> None:
        outcome = self.gateway.submit(_request("agent-admin", "data_platform", "delete_logs"))
        self.assertEqual(outcome.verdict, PolicyVerdict.DENY)
        self.assertEqual(self.proxy.calls, [])

    def test_proxy_failure_is_audited_and_never_bypassed(self) -> None:
        self.proxy.fail = True
        outcome = self.gateway.submit(_request("agent-admin", "okta", "list_users"))
        self.assertFalse(outcome.executed)
        self.assertIsNotNone(outcome.error)
        errors = self.events.read_from(kind=EventKind.PLATFORM_ERROR)
        self.assertEqual(len(errors), 1)
        self.assertEqual(len(self.events.read_from(kind=EventKind.ACTION_EXECUTED)), 0)

    def test_timeout_sweep_never_executes(self) -> None:
        outcome = self.gateway.submit(_request("agent-admin", "okta", "suspend_user"))
        # Active policy timeout is 3600s; now = 2h after the captured request ts.
        swept = self.gateway.sweep_timeouts(now_iso="2026-06-12T12:00:00Z")
        self.assertEqual(swept, [outcome.event_id])
        self.assertEqual(self.proxy.calls, [])
        resolved = self.events.read_from(kind=EventKind.APPROVAL_RESOLVED)
        self.assertEqual(resolved[0].payload["approval_state"], ApprovalState.TIMEOUT)


if __name__ == "__main__":
    unittest.main()
