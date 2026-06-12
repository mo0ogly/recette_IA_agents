"""End-to-end governed-flow recette against a LIVE AgentRail API (L1, R14 proof).

Opt-in: runs only when AGENTRAIL_E2E_API_URL points at a running API (the
docker `e2e` service sets it to http://api:8090). Without the variable the
whole module is skipped, so `python -m unittest discover -s tests` stays green
offline.

Covered paths (one full pass over the Gateway flow, I2/I5/I6/I1):
- escalate -> pending -> human approve -> executed via the lab proxy
- deny for an unprivileged role (deny-by-default)
- pure DENY catalog row (no privileged escape hatch)
- escalate -> approval timeout via the sweep endpoint
- audit hash-chain verification + presence of every expected event kind

Uses the stdlib HTTP client (no httpx dependency) and unique per-run resource
strings so reruns against a persistent volume stay unambiguous. uuid4 here is
test-harness input, not decision-path randomness (I4 applies to the platform).
"""

from __future__ import annotations

import os
import time
import unittest
import uuid
from typing import Any

from recette._http_client import StdlibHttpClient

API_URL = os.environ.get("AGENTRAIL_E2E_API_URL", "")

ADMIN_ID = "e2e-admin"
BOT_ID = "e2e-bot"

EXPECTED_KINDS = {"action_requested", "action_denied", "approval_resolved", "action_executed"}


@unittest.skipUnless(API_URL, "AGENTRAIL_E2E_API_URL not set: e2e suite is opt-in")
class GovernedFlowE2E(unittest.TestCase):
    """Ordered scenario: each numbered step builds on the previous one."""

    client: StdlibHttpClient
    run_id: str = ""
    approved_event_id: str = ""
    timeout_event_id: str = ""

    @classmethod
    def setUpClass(cls) -> None:
        cls.client = StdlibHttpClient(API_URL, timeout=30.0)
        cls.run_id = uuid.uuid4().hex[:12]
        cls._wait_for_api()

    @classmethod
    def _wait_for_api(cls, attempts: int = 30, delay: float = 1.0) -> None:
        last_error = "no attempt made"
        for _ in range(attempts):
            try:
                resp = cls.client.get("/health")
                if resp.status == 200:
                    return
                last_error = f"HTTP {resp.status}"
            except Exception as exc:  # noqa: BLE001 - startup polling
                last_error = str(exc)
            time.sleep(delay)
        raise RuntimeError(f"API at {API_URL} not reachable: {last_error}")

    # --- helpers ---

    def _register_agent(self, agent_id: str, role: str) -> None:
        resp = self.client.post(
            "/config/agents",
            json={
                "id": agent_id,
                "runtime": "lab",
                "role": role,
                "capability_scope": ["okta"],
            },
        )
        if resp.status in (200, 201):
            return
        # Rerun against a persistent volume: the agent already exists.
        if resp.status == 400 and "already exists" in str(resp.json().get("detail", "")):
            return
        self.fail(f"agent registration {agent_id!r} failed: HTTP {resp.status} {resp.json()}")

    def _execute(
        self, agent_id: str, target_system: str, action_type: str, resource: str
    ) -> tuple[int, dict[str, Any]]:
        resp = self.client.post(
            "/actions/execute",
            json={
                "agent_id": agent_id,
                "action_type": action_type,
                "target_system": target_system,
                "resource": resource,
                "payload": {"run_id": self.run_id},
            },
        )
        body = resp.json()
        self.assertIsInstance(body, dict, f"unexpected body: {body!r}")
        return resp.status, body

    def _require(self, attribute: str) -> str:
        value = getattr(type(self), attribute, "")
        if not value:
            self.skipTest(f"prerequisite step did not record {attribute!r}")
        return str(value)

    # --- a/b: agent provisioning ---

    def test_01_register_agents(self) -> None:
        self._register_agent(ADMIN_ID, "identity_admin")
        self._register_agent(BOT_ID, "marketing_bot")
        agents = self.client.get("/config/agents").json()
        ids = {a["id"] for a in agents}
        self.assertLessEqual({ADMIN_ID, BOT_ID}, ids)

    # --- c: privileged role escalates to pending (I6) ---

    def test_02_escalate_goes_pending(self) -> None:
        status, body = self._execute(
            ADMIN_ID, "okta", "suspend_user", f"user:e2e-{self.run_id}-suspend"
        )
        self.assertEqual(status, 202, body)
        self.assertEqual(body["verdict"], "escalate", body)
        self.assertEqual(body["approval_state"], "pending", body)
        self.assertFalse(body["executed"], body)
        type(self).approved_event_id = str(body["event_id"])

    # --- d: pending inbox contains the event ---

    def test_03_pending_inbox_lists_event(self) -> None:
        event_id = self._require("approved_event_id")
        pending = self.client.get("/approvals?state=pending").json()["pending"]
        mine = [p for p in pending if p["event_id"] == event_id]
        self.assertEqual(len(mine), 1, f"event {event_id} not in pending inbox: {pending}")
        self.assertEqual(mine[0]["resource"], f"user:e2e-{self.run_id}-suspend")

    # --- e: human approval executes via the lab proxy (I5) ---

    def test_04_approve_executes_action(self) -> None:
        event_id = self._require("approved_event_id")
        resp = self.client.post(
            f"/approvals/{event_id}/approve", json={"approver": "e2e", "reason": "test"}
        )
        body = resp.json()
        self.assertEqual(resp.status, 200, body)
        self.assertEqual(body["approval_state"], "approved", body)
        self.assertTrue(body["executed"], body)
        self.assertIsNotNone(body["side_effect_hash"], body)

    # --- f: unprivileged role is denied (deny-by-default) ---

    def test_05_unprivileged_role_denied(self) -> None:
        status, body = self._execute(BOT_ID, "okta", "suspend_user", f"user:e2e-{self.run_id}-bot")
        self.assertEqual(status, 200, body)
        self.assertEqual(body["verdict"], "deny", body)
        self.assertFalse(body["executed"], body)
        self.assertIsNone(body["side_effect_hash"], body)

    # --- g: pure DENY row has no privileged escape hatch ---

    def test_06_pure_deny_row_denied_for_admin(self) -> None:
        status, body = self._execute(
            ADMIN_ID, "data_platform", "delete_logs", f"logs:e2e-{self.run_id}"
        )
        self.assertEqual(status, 200, body)
        self.assertEqual(body["verdict"], "deny", body)
        self.assertFalse(body["executed"], body)

    # --- h: pending approval expires via the timeout sweep (I6, I4 captured now) ---

    def test_07_timeout_sweep_resolves_pending(self) -> None:
        status, body = self._execute(
            ADMIN_ID, "okta", "reset_password", f"user:e2e-{self.run_id}-timeout"
        )
        self.assertEqual(status, 202, body)
        self.assertEqual(body["approval_state"], "pending", body)
        type(self).timeout_event_id = str(body["event_id"])

        sweep = self.client.post("/approvals/sweep-timeouts", json={"now": "2030-01-01T00:00:00Z"})
        swept = sweep.json()
        self.assertEqual(sweep.status, 200, swept)
        self.assertIn(self.timeout_event_id, swept["timed_out"], swept)

        action = self.client.get(f"/actions/{self.timeout_event_id}").json()
        self.assertEqual(action.get("resolution"), "timeout", action)

    # --- i: audit plane proof (I1 hash chain + every kind present) ---

    def test_08_audit_chain_verifies(self) -> None:
        report = self.client.get("/audit/verify").json()
        self.assertTrue(report["ok"], report)
        self.assertGreater(report["checked"], 0, report)

    def test_09_audit_log_contains_all_kinds(self) -> None:
        events = self.client.get("/audit/events").json()["events"]
        kinds = {e["kind"] for e in events}
        self.assertLessEqual(EXPECTED_KINDS, kinds, f"missing kinds: {EXPECTED_KINDS - kinds}")


if __name__ == "__main__":
    unittest.main()
