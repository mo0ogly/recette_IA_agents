"""I6 durability: a pending approval survives a process restart.

The approval inbox is a fold over the append-only event log (I1), so it is durable
by construction -- but the existing suite proves this only within one process using
an in-memory store. This test proves it against a PERSISTED SqliteEventStore across
a simulated restart: every gateway/service object is dropped and rebuilt from a fresh
store pointing at the SAME database file, exactly as a real process restart would.

Proven across the restart boundary:
  - an escalated action stays pending and reappears in the rebuilt inbox;
  - resolving it (approve) is itself durable;
  - a second resolution after restart is refused (no double-approve, I6);
  - a timeout sweep after restart resolves to TIMEOUT, never approve, never executes.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from recette.platform.approvals import ApprovalService, InvalidTransition
from recette.platform.approvals.state_machine import ApprovalAction
from recette.platform.catalog import Catalog
from recette.platform.catalog.model import ActionSpec, Criticality, RiskLevel
from recette.platform.events import ApprovalState, EventKind, PolicyVerdict
from recette.platform.eventstore import EventStore, SqliteEventStore
from recette.platform.gateway import ActionRequest, AgentResolver, Gateway
from recette.platform.policy.model import baseline_from_catalog
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
)
AGENTS = {
    "agent-admin": {"id": "agent-admin", "role": "identity_admin", "capability_scope": ["okta"]},
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


class _RestartSafeIds:
    """Event ids that stay unique across a restart by offsetting from the log size,
    mirroring the production RestartSafeIdGenerator (event_id is UNIQUE in SQLite)."""

    def __init__(self, store: EventStore) -> None:
        self._base = (len(store.read_from()) + 1) * 1_000_000
        self._n = 0

    def next_id(self) -> str:
        self._n += 1
        return f"EV{self._base + self._n:024d}"


class TestApprovalDurability(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._db = Path(self._tmp.name) / "events.db"
        self._policy_dir = Path(self._tmp.name) / "policies"
        self.catalog = Catalog(SPECS)
        policies = PolicyStore(self._policy_dir)
        policies.publish(baseline_from_catalog(self.catalog, version="v-test"))

    def _open_store(self) -> SqliteEventStore:
        # Close every store deterministically at teardown BEFORE the tempdir is
        # removed. addCleanup is LIFO and self._tmp.cleanup was registered first
        # (setUp), so it runs last -- all connections are closed before the dir is
        # deleted. On Windows an open SQLite handle would otherwise lock the file
        # and fail the tempdir cleanup (WinError 32).
        store = SqliteEventStore(self._db)
        self.addCleanup(store.close)
        return store

    def _gateway(self, store: EventStore, proxy: _RecordingProxy) -> Gateway:
        # A FRESH policy store + gateway each call: this is the "process restart" --
        # nothing in memory carries over, everything is rebuilt from the SQLite file.
        policies = PolicyStore(self._policy_dir)
        return Gateway(
            catalog=self.catalog,
            policy_store=policies,
            event_store=store,
            proxy=proxy,
            id_generator=_RestartSafeIds(store),
            agent_resolver=AgentResolver(lambda agent_id: AGENTS.get(agent_id)),
        )

    def _escalate(self) -> str:
        store = self._open_store()
        gateway = self._gateway(store, _RecordingProxy())
        outcome = gateway.submit(
            ActionRequest(
                agent_id="agent-admin",
                action_type="suspend_user",
                target_system="okta",
                resource="org/acme",
                payload={"reason": "test"},
                timestamp="2026-06-13T10:00:00Z",
            )
        )
        self.assertEqual(outcome.approval_state, ApprovalState.PENDING)
        return outcome.event_id

    def test_pending_survives_restart(self) -> None:
        pending_id = self._escalate()
        # "Restart": brand-new store object on the same file, fresh service.
        service = ApprovalService(self._open_store())
        pendings = {p.event_id for p in service.pending()}
        self.assertIn(pending_id, pendings)

    def test_resolution_survives_restart_and_double_resolve_refused(self) -> None:
        pending_id = self._escalate()
        # Restart 1: resolve (approve) through a rebuilt gateway.
        proxy = _RecordingProxy()
        gw2 = self._gateway(self._open_store(), proxy)
        out = gw2.resolve_approval(
            pending_event_id=pending_id,
            action=ApprovalAction.APPROVE,
            approver="alice",
            reason=None,
        )
        self.assertEqual(out.approval_state, ApprovalState.APPROVED)
        self.assertTrue(out.executed)
        self.assertEqual(proxy.calls, ["okta/suspend_user"])
        # Restart 2: the resolution is durable, and re-approving is refused (I6).
        service = ApprovalService(self._open_store())
        self.assertEqual(service.resolved_ids().get(pending_id), ApprovalState.APPROVED)
        self.assertNotIn(pending_id, {p.event_id for p in service.pending()})
        gw3 = self._gateway(self._open_store(), _RecordingProxy())
        with self.assertRaises(InvalidTransition):
            gw3.resolve_approval(
                pending_event_id=pending_id,
                action=ApprovalAction.APPROVE,
                approver="mallory",
                reason=None,
            )

    def test_timeout_sweep_after_restart_never_approves_never_executes(self) -> None:
        pending_id = self._escalate()
        # Restart: a sweep with a now far past the timeout resolves to TIMEOUT.
        proxy = _RecordingProxy()
        gw2 = self._gateway(self._open_store(), proxy)
        timed_out = gw2.sweep_timeouts(now_iso="2999-01-01T00:00:00Z")
        self.assertIn(pending_id, timed_out)
        self.assertEqual(proxy.calls, [])  # never executed (I6, never auto-approve)
        service = ApprovalService(self._open_store())
        self.assertEqual(service.resolved_ids().get(pending_id), ApprovalState.TIMEOUT)

    def test_no_appended_action_executed_event_for_timeout(self) -> None:
        pending_id = self._escalate()
        gw2 = self._gateway(self._open_store(), _RecordingProxy())
        gw2.sweep_timeouts(now_iso="2999-01-01T00:00:00Z")
        executed = list(self._open_store().read_from(kind=EventKind.ACTION_EXECUTED))
        self.assertEqual(
            [e for e in executed if e.payload.get("agent_id") == "agent-admin"],
            [],
            f"a timed-out action {pending_id} must never produce an executed event",
        )


if __name__ == "__main__":
    unittest.main()
