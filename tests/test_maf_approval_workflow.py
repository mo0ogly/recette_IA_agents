"""A MAF gated tool invocation flows through the REAL approval workflow (I6).

Uses the committed catalog (load_catalog, which now includes the mcp domain) and
the existing Gateway / ApprovalService: a tool_operator invoking an MCP tool
escalates to a pending human approval, executes only after approve, and a
non-privileged role is denied. No new approval machinery -- the MAF gated
capability is wired onto the platform's existing I6 pipeline.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from recette.platform.approvals.service import ApprovalService
from recette.platform.approvals.state_machine import ApprovalAction
from recette.platform.catalog import load_catalog
from recette.platform.events import ApprovalState, EventKind, PolicyVerdict
from recette.platform.eventstore.memory_store import InMemoryEventStore
from recette.platform.gateway import ActionRequest, AgentResolver, Gateway
from recette.platform.ids import SequenceIdGenerator
from recette.platform.policy.model import baseline_from_catalog
from recette.platform.policy.store import PolicyStore
from recette.platform.proxy.protocol import ExecutionResult, side_effect_hash

AGENTS = {
    "maf-agent": {"id": "maf-agent", "role": "tool_operator", "capability_scope": ["mcp"]},
    "maf-bot": {"id": "maf-bot", "role": "marketing_bot", "capability_scope": []},
}


class _RecordingProxy:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def execute(self, event) -> ExecutionResult:  # type: ignore[no-untyped-def]
        self.calls.append(f"{event.target_system}/{event.action_type}")
        response = {"done": True}
        return ExecutionResult(
            ok=True,
            status_code=200,
            response=response,
            side_effect_hash=side_effect_hash(
                event.target_system, event.action_type, event.resource, response
            ),
        )


def _invoke_tool(agent_id: str) -> ActionRequest:
    return ActionRequest(
        agent_id=agent_id,
        action_type="invoke_tool",
        target_system="mcp",
        resource="mcp/diagnostic-server",
        payload={"tool": "restart_service"},
        timestamp="2026-06-13T10:00:00Z",
    )


class TestMafApprovalWorkflow(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.catalog = load_catalog()  # the real catalog, includes the mcp domain
        self.policy_store = PolicyStore(Path(self._tmp.name))
        self.policy_store.publish(baseline_from_catalog(self.catalog, version="v-test"))
        self.events = InMemoryEventStore()
        self.proxy = _RecordingProxy()
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

    def test_catalog_governs_mcp_invoke_tool(self) -> None:
        spec = self.catalog.get("mcp", "invoke_tool")
        self.assertIsNotNone(spec)
        self.assertEqual(spec.verdict_privileged, PolicyVerdict.ESCALATE)

    def test_gated_tool_escalates_then_executes_on_approval(self) -> None:
        outcome = self.gateway.submit(_invoke_tool("maf-agent"))
        self.assertEqual(outcome.verdict, PolicyVerdict.ESCALATE)
        self.assertEqual(outcome.approval_state, ApprovalState.PENDING)
        self.assertFalse(outcome.executed)
        self.assertEqual(self.proxy.calls, [])  # I6: nothing runs while pending

        # The action appears in the existing approval inbox.
        pending = ApprovalService(self.events).pending()
        self.assertIn(outcome.event_id, [p.event_id for p in pending])

        resolved = self.gateway.resolve_approval(
            pending_event_id=outcome.event_id,
            action=ApprovalAction.APPROVE,
            approver="user:rssi",
            reason="ticket-mcp-1",
        )
        self.assertTrue(resolved.executed)
        self.assertEqual(self.proxy.calls, ["mcp/invoke_tool"])

    def test_denied_approval_never_executes(self) -> None:
        outcome = self.gateway.submit(_invoke_tool("maf-agent"))
        resolved = self.gateway.resolve_approval(
            pending_event_id=outcome.event_id,
            action=ApprovalAction.DENY,
            approver="user:rssi",
            reason="no",
        )
        self.assertFalse(resolved.executed)
        self.assertEqual(resolved.approval_state, ApprovalState.DENIED)
        self.assertEqual(self.proxy.calls, [])

    def test_non_privileged_role_denied(self) -> None:
        outcome = self.gateway.submit(_invoke_tool("maf-bot"))
        self.assertEqual(outcome.verdict, PolicyVerdict.DENY)
        self.assertEqual(self.proxy.calls, [])
        self.assertEqual(len(self.events.read_from(kind=EventKind.ACTION_DENIED)), 1)

    def test_timeout_never_auto_approves(self) -> None:
        outcome = self.gateway.submit(_invoke_tool("maf-agent"))
        swept = self.gateway.sweep_timeouts(now_iso="2026-06-13T12:00:00Z")
        self.assertEqual(swept, [outcome.event_id])
        self.assertEqual(self.proxy.calls, [])  # fail-safe: timeout != approve


if __name__ == "__main__":
    unittest.main()
