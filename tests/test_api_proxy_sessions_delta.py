# tests/test_api_proxy_sessions_delta.py
"""GET /proxy/sessions/delta -- coalesced SessionsPanel poll (traces+wire+reconcile).

One round trip replaces the panel's three proxy-owned calls (getProxyTraces +
getWireFlows + getReconcile). Container-free: traces are seeded through the
governed /actions/execute path (stub proxy) and wire flows through the
POST /proxy/wire ingest, so the coalesced envelope is verified without a live
mitmproxy. Cursors are independent per side (since_seq for traces,
wire_since_seq for wire) with the same reset semantics as the per-source
endpoints. run_id scopes WIRE (and reconcile) only -- traces stay unfiltered,
mirroring the panel's client-side grouping.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover - depends on the [api] extra
    _HAS_FASTAPI = False

from recette.api.config_store import ConfigStore
from recette.platform.catalog import Catalog
from recette.platform.catalog.model import ActionSpec, Criticality, RiskLevel
from recette.platform.events import PolicyVerdict
from recette.platform.eventstore.memory_store import InMemoryEventStore
from recette.platform.policy.store import PolicyStore
from recette.platform.proxy.protocol import ExecutionResult, side_effect_hash

if _HAS_FASTAPI:
    from recette.api.app import create_app

SPECS = (
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
)


class _StubProxy:
    """Deterministic proxy double producing a successful ExecutionResult."""

    def execute(self, event):  # type: ignore[no-untyped-def]
        response = {"done": True}
        return ExecutionResult(
            ok=True,
            status_code=200,
            response=response,
            side_effect_hash=side_effect_hash(
                event.target_system, event.action_type, event.resource, response
            ),
        )


def _flow(**over: object) -> dict:
    base = {
        "method": "POST",
        "scheme": "http",
        "host": "localhost",
        "port": 8082,
        "path": "/github/execute",
        "status_code": 200,
        "content_type": "application/json",
        "request_body": '{"action_type":"open_pr"}',
        "response_body": '{"success":true}',
    }
    base.update(over)
    return base


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class SessionsDeltaEndpointTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        os.environ["INSPECT_IA_AGENTS_PROXY_DEBUG"] = "on"
        self.addCleanup(lambda: os.environ.pop("INSPECT_IA_AGENTS_PROXY_DEBUG", None))
        tmp = Path(self._tmp.name)
        app = create_app(
            config_store=ConfigStore(tmp / "config.json"),
            event_store=InMemoryEventStore(),
            policy_store=PolicyStore(tmp / "policies"),
            proxy=_StubProxy(),
            catalog=Catalog(SPECS),
        )
        self.client = TestClient(app)
        resp = self.client.post(
            "/config/agents",
            json={
                "id": "agent-admin",
                "runtime": "lab",
                "role": "identity_admin",
                "capability_scope": ["okta"],
            },
        )
        self.assertEqual(resp.status_code, 201, resp.text)

    def _execute(self, payload: dict | None = None):  # type: ignore[no-untyped-def]
        resp = self.client.post(
            "/actions/execute",
            json={
                "agent_id": "agent-admin",
                "action_type": "list_users",
                "target_system": "okta",
                "resource": "org/acme",
                "payload": payload if payload is not None else {"reason": "test"},
            },
        )
        self.assertEqual(resp.status_code, 200, resp.text)

    def _ingest(self, **over: object) -> None:
        resp = self.client.post("/proxy/wire", json=_flow(**over))
        self.assertEqual(resp.status_code, 201, resp.text)

    def test_first_call_without_cursors_serves_full_snapshot(self) -> None:
        # No cursors -> full traces + full wire + the reconcile verdict, all
        # envelope keys present (the panel's cold start, one round trip).
        self._execute()
        self._execute()
        self._ingest(path="/a")
        self._ingest(path="/b")
        body = self.client.get("/proxy/sessions/delta").json()
        self.assertTrue(body["debug_enabled"])
        self.assertEqual([t["seq"] for t in body["traces"]], [1, 2])
        self.assertEqual(body["last_seq"], 2)
        self.assertFalse(body["reset"])
        self.assertEqual([f["seq"] for f in body["wire_flows"]], [1, 2])
        self.assertEqual(body["wire_last_seq"], 2)
        self.assertFalse(body["wire_reset"])
        reconcile = body["reconcile"]
        self.assertIsInstance(reconcile["ok"], bool)
        self.assertIsInstance(reconcile["bypass_flows"], list)
        self.assertIsInstance(reconcile["audited_run_ids"], list)
        self.assertIsNone(reconcile["run_id"])
        self.assertTrue(reconcile["strict"])

    def test_incremental_cursors_return_only_new_items(self) -> None:
        self._execute()
        self._execute()
        self._ingest(path="/a")
        first = self.client.get("/proxy/sessions/delta").json()
        self.assertEqual(first["last_seq"], 2)
        self.assertEqual(first["wire_last_seq"], 1)
        # Seed more on both sides, poll with both cursors.
        self._execute()
        self._ingest(path="/b")
        body = self.client.get(
            "/proxy/sessions/delta",
            params={"since_seq": 2, "wire_since_seq": 1},
        ).json()
        self.assertEqual([t["seq"] for t in body["traces"]], [3])
        self.assertEqual(body["last_seq"], 3)
        self.assertFalse(body["reset"])
        self.assertEqual([f["seq"] for f in body["wire_flows"]], [2])
        self.assertEqual(body["wire_last_seq"], 2)
        self.assertFalse(body["wire_reset"])

    def test_run_id_scopes_wire_but_not_traces(self) -> None:
        # The panel groups ALL traces client-side but scopes wire (+ reconcile)
        # to the deep-linked run: run_id filters WIRE only, traces stay full.
        self._execute()
        self._execute()
        self._ingest(path="/a", run_id="run-1")
        self._ingest(path="/b", run_id="run-2")
        body = self.client.get("/proxy/sessions/delta", params={"run_id": "run-1"}).json()
        self.assertEqual(len(body["traces"]), 2)  # NOT filtered by run_id
        self.assertEqual([f["run_id"] for f in body["wire_flows"]], ["run-1"])
        self.assertEqual(body["reconcile"]["run_id"], "run-1")

    def test_reset_cursors_are_independent(self) -> None:
        # A stale traces cursor resets the traces side only; the valid wire
        # cursor stays incremental (independent cursors, one call).
        for _ in range(3):
            self._execute()
        for p in ("/a", "/b", "/c"):
            self._ingest(path=p)
        body = self.client.get(
            "/proxy/sessions/delta",
            params={"since_seq": 999, "wire_since_seq": 2},
        ).json()
        self.assertTrue(body["reset"])
        self.assertEqual([t["seq"] for t in body["traces"]], [1, 2, 3])
        self.assertEqual(body["last_seq"], 3)
        self.assertFalse(body["wire_reset"])
        self.assertEqual([f["seq"] for f in body["wire_flows"]], [3])
        self.assertEqual(body["wire_last_seq"], 3)

    def test_strict_defaults_true_and_false_is_honored(self) -> None:
        # SessionsPanel calls getReconcile(runParam, true) today: strict is the
        # default; an explicit strict=false is passed through unchanged.
        default = self.client.get("/proxy/sessions/delta").json()
        self.assertTrue(default["reconcile"]["strict"])
        relaxed = self.client.get("/proxy/sessions/delta", params={"strict": "false"}).json()
        self.assertFalse(relaxed["reconcile"]["strict"])

    def test_redaction_applies_to_both_traces_and_wire(self) -> None:
        # Both views emit through _redacted_view: a Bearer credential is masked
        # in the trace payload and in the wire request body (VIEW only).
        secret = "secrettoken" + "123"
        self._execute(payload={"reason": f"Bearer {secret}"})
        self._ingest(request_body=f"Bearer {secret}")
        body = self.client.get("/proxy/sessions/delta").json()
        trace_payload = str(body["traces"][0]["request_payload"])
        self.assertNotIn(secret, trace_payload)
        self.assertIn("***REDACTED***", trace_payload)
        wire_body = body["wire_flows"][0]["request_body"]
        self.assertNotIn(secret, wire_body)
        self.assertIn("***REDACTED***", wire_body)


if __name__ == "__main__":
    unittest.main()
