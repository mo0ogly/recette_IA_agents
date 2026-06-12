"""A1: governed-execution API tests (actions, policies, approvals, audit, catalog).

The catalog is injected so the tests never depend on the domain modules being
populated (parallel workstreams). The proxy is a deterministic stub: no real
side effect, no network (I5 lab posture).
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover - exercised only without the [api] extra
    _HAS_FASTAPI = False

from recette.api.config_store import ConfigStore
from recette.platform.catalog import Catalog
from recette.platform.catalog.model import ActionSpec, RiskLevel
from recette.platform.events import PolicyVerdict
from recette.platform.eventstore.memory_store import InMemoryEventStore
from recette.platform.policy.store import PolicyStore
from recette.platform.proxy.protocol import ExecutionResult, side_effect_hash

SPECS = (
    ActionSpec(
        target_system="okta",
        action_type="suspend_user",
        risk_level=RiskLevel.HIGH,
        verdict_privileged=PolicyVerdict.ESCALATE,
        verdict_default=PolicyVerdict.DENY,
        privileged_roles=("identity_admin",),
        description="Suspend an Okta user",
    ),
    ActionSpec(
        target_system="okta",
        action_type="list_users",
        risk_level=RiskLevel.LOW,
        verdict_privileged=PolicyVerdict.ALLOW,
        verdict_default=PolicyVerdict.DENY,
        privileged_roles=("identity_admin",),
        description="List users (read-only)",
    ),
)

V2_POLICY_DOC = {
    "version": "v2",
    "approval_timeout_seconds": 600,
    "rules": [
        {
            "rule_id": "okta.list_users.identity_admin",
            "target_system": "okta",
            "action_type": "list_users",
            "role": "identity_admin",
            "verdict": "allow",
            "risk_level": "low",
        }
    ],
}


class StubProxy:
    """Deterministic in-test proxy: records calls, never touches the network."""

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


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class TestPlatformApi(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tmp = Path(self._tmp.name)
        self.proxy = StubProxy()
        self.app = create_app(
            config_store=ConfigStore(tmp / "config.json"),
            event_store=InMemoryEventStore(),
            policy_store=PolicyStore(tmp / "policies"),
            proxy=self.proxy,
            catalog=Catalog(SPECS),
        )
        self.client = TestClient(self.app)
        for agent in (
            {
                "id": "agent-admin",
                "runtime": "lab",
                "role": "identity_admin",
                "capability_scope": ["okta"],
            },
            {"id": "agent-bot", "runtime": "lab", "role": "marketing_bot", "capability_scope": []},
        ):
            resp = self.client.post("/config/agents", json=agent)
            self.assertEqual(resp.status_code, 201, resp.text)

    def _execute(self, agent_id: str, action_type: str):  # type: ignore[no-untyped-def]
        return self.client.post(
            "/actions/execute",
            json={
                "agent_id": agent_id,
                "action_type": action_type,
                "target_system": "okta",
                "resource": "org/acme",
                "payload": {"reason": "test"},
            },
        )

    def test_allow_executes_with_side_effect_hash(self) -> None:
        resp = self._execute("agent-admin", "list_users")
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["verdict"], "allow")
        self.assertTrue(body["executed"])
        self.assertIsNotNone(body["side_effect_hash"])
        self.assertEqual(self.proxy.calls, ["okta/list_users"])

    def test_escalate_then_approve_executes(self) -> None:
        resp = self._execute("agent-admin", "suspend_user")
        self.assertEqual(resp.status_code, 202, resp.text)
        body = resp.json()
        self.assertEqual(body["approval_state"], "pending")
        self.assertFalse(body["executed"])
        self.assertEqual(self.proxy.calls, [])  # I6: nothing runs while pending
        event_id = body["event_id"]

        inbox = self.client.get("/approvals").json()
        self.assertEqual([p["event_id"] for p in inbox["pending"]], [event_id])

        lookup = self.client.get(f"/actions/{event_id}").json()
        self.assertIsNone(lookup["resolution"])

        approved = self.client.post(
            f"/approvals/{event_id}/approve",
            json={"approver": "user:rssi", "reason": "ticket-42"},
        )
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertTrue(approved.json()["executed"])
        self.assertEqual(self.proxy.calls, ["okta/suspend_user"])

        lookup = self.client.get(f"/actions/{event_id}").json()
        self.assertEqual(lookup["resolution"], "approved")

    def test_deny_for_unprivileged_role(self) -> None:
        resp = self._execute("agent-bot", "suspend_user")
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["verdict"], "deny")
        self.assertFalse(body["executed"])
        self.assertEqual(self.proxy.calls, [])

    def test_double_approve_is_conflict(self) -> None:
        event_id = self._execute("agent-admin", "suspend_user").json()["event_id"]
        first = self.client.post(f"/approvals/{event_id}/approve", json={"approver": "u"})
        self.assertEqual(first.status_code, 200, first.text)
        second = self.client.post(f"/approvals/{event_id}/approve", json={"approver": "u"})
        self.assertEqual(second.status_code, 409, second.text)

    def test_approve_unknown_event_is_404(self) -> None:
        resp = self.client.post("/approvals/EVnope/approve", json={"approver": "u"})
        self.assertEqual(resp.status_code, 404, resp.text)

    def test_audit_chain_and_verify(self) -> None:
        self._execute("agent-admin", "list_users")
        self._execute("agent-bot", "suspend_user")
        events = self.client.get("/audit/events").json()["events"]
        kinds = [e["kind"] for e in events]
        self.assertIn("action_executed", kinds)
        self.assertIn("action_denied", kinds)
        filtered = self.client.get("/audit/events", params={"kind": "action_denied"}).json()
        self.assertEqual([e["kind"] for e in filtered["events"]], ["action_denied"])
        report = self.client.get("/audit/verify").json()
        self.assertTrue(report["ok"])
        self.assertEqual(report["checked"], len(events))

    def test_audit_events_filter_by_event_id(self) -> None:
        self._execute("agent-admin", "list_users")
        self._execute("agent-bot", "suspend_user")
        events = self.client.get("/audit/events").json()["events"]
        self.assertGreater(len(events), 1)
        known = events[0]["event_id"]

        # A known event_id returns exactly that one event.
        single = self.client.get(
            "/audit/events", params={"event_id": known}
        ).json()["events"]
        self.assertEqual([e["event_id"] for e in single], [known])

        # An unknown event_id returns an empty list (no error, read-only I1).
        unknown = self.client.get(
            "/audit/events", params={"event_id": "EVnope"}
        ).json()["events"]
        self.assertEqual(unknown, [])

        # event_id combines with other filters: a matching kind keeps the event,
        # a non-matching kind filters it out.
        kind = events[0]["kind"]
        keep = self.client.get(
            "/audit/events", params={"event_id": known, "kind": kind}
        ).json()["events"]
        self.assertEqual([e["event_id"] for e in keep], [known])
        drop = self.client.get(
            "/audit/events",
            params={"event_id": known, "kind": "platform_error"},
        ).json()["events"]
        self.assertEqual(drop, [])

    def test_audit_events_tail_returns_last_n(self) -> None:
        # 5 governed flows -> at least 5 audited events on the store.
        for _ in range(5):
            self._execute("agent-admin", "list_users")
        events = self.client.get("/audit/events").json()["events"]
        self.assertGreaterEqual(len(events), 5)

        # tail=3 returns the LAST 3 by seq (not the first 3), still ascending.
        tail = self.client.get("/audit/events", params={"tail": 3}).json()["events"]
        self.assertEqual([e["seq"] for e in tail], [e["seq"] for e in events[-3:]])

        # tail composes with filters: last 2 of the kind-filtered set.
        executed = self.client.get(
            "/audit/events", params={"kind": "action_executed"}
        ).json()["events"]
        tail_executed = self.client.get(
            "/audit/events", params={"kind": "action_executed", "tail": 2}
        ).json()["events"]
        self.assertEqual(
            [e["seq"] for e in tail_executed], [e["seq"] for e in executed[-2:]]
        )

    def test_audit_events_tail_and_limit_conflict_is_400(self) -> None:
        resp = self.client.get("/audit/events", params={"tail": 3, "limit": 3})
        self.assertEqual(resp.status_code, 400, resp.text)

    def test_audit_export_jsonl(self) -> None:
        self._execute("agent-admin", "list_users")
        self._execute("agent-bot", "suspend_user")
        events = self.client.get("/audit/events").json()["events"]
        self.assertGreater(len(events), 0)

        resp = self.client.get("/audit/export.jsonl")
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertTrue(resp.headers["content-type"].startswith("application/x-ndjson"))

        lines = [line for line in resp.text.split("\n") if line]
        self.assertEqual(len(lines), len(events))
        parsed = [json.loads(line) for line in lines]
        seqs = [p["seq"] for p in parsed]
        self.assertEqual(seqs, sorted(seqs))
        self.assertEqual(parsed[0]["event_id"], events[0]["event_id"])

    def test_catalog_actions_listing(self) -> None:
        resp = self.client.get("/catalog/actions")
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["count"], 2)
        self.assertEqual(len(body["actions"]), 2)
        none = self.client.get("/catalog/actions", params={"target_system": "slack"}).json()
        self.assertEqual(none["count"], 0)

    def test_policy_lifecycle(self) -> None:
        listing = self.client.get("/policies").json()
        self.assertIn("v1", listing["versions"])  # bootstrap baseline from injected catalog
        self.assertEqual(listing["active"], "v1")

        created = self.client.post("/policies", json=V2_POLICY_DOC)
        self.assertEqual(created.status_code, 201, created.text)

        activated = self.client.put("/policies/active", json={"version": "v2"})
        self.assertEqual(activated.status_code, 200, activated.text)
        active = self.client.get("/policies/active").json()
        self.assertEqual(active["version"], "v2")

        duplicate = self.client.post("/policies", json=V2_POLICY_DOC)
        self.assertEqual(duplicate.status_code, 409, duplicate.text)

        missing = self.client.put("/policies/active", json={"version": "v999"})
        self.assertEqual(missing.status_code, 404, missing.text)
        malformed = self.client.post("/policies", json={"version": "v3"})
        self.assertEqual(malformed.status_code, 400, malformed.text)
        unknown = self.client.get("/policies/v999")
        self.assertEqual(unknown.status_code, 404, unknown.text)

    def test_get_unknown_action_event_is_404(self) -> None:
        resp = self.client.get("/actions/EVdoes-not-exist")
        self.assertEqual(resp.status_code, 404, resp.text)

    def test_execute_missing_fields_is_400(self) -> None:
        resp = self.client.post("/actions/execute", json={"agent_id": "agent-admin"})
        self.assertEqual(resp.status_code, 400, resp.text)

    def test_sweep_timeouts_with_captured_now(self) -> None:
        event_id = self._execute("agent-admin", "suspend_user").json()["event_id"]
        # Baseline timeout is 3600s; a 'now' far in the future expires the pending.
        swept = self.client.post("/approvals/sweep-timeouts", json={"now": "2199-01-01T00:00:00Z"})
        self.assertEqual(swept.status_code, 200, swept.text)
        self.assertEqual(swept.json()["timed_out"], [event_id])
        self.assertEqual(self.proxy.calls, [])  # timeout never executes (I6)


if __name__ == "__main__":
    unittest.main()
