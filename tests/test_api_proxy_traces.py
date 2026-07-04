# tests/test_api_proxy_traces.py
"""S5: GET /proxy/traces exposes the debug trace ring (I5 observability).

With INSPECT_IA_AGENTS_PROXY_DEBUG on, the gateway's TracingProxy records each executed
side effect; the endpoint serves those traces (read-only) for the Monaco console.
With debug off, no trace is recorded. DELETE clears the buffer (not the audit log, I1).
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
    """Deterministic proxy double: a payload carrying ``fail`` produces a
    failed ExecutionResult so the trace buffer holds both outcomes."""

    def execute(self, event):  # type: ignore[no-untyped-def]
        if event.payload.get("fail"):
            return ExecutionResult(
                ok=False,
                status_code=500,
                response={"done": False},
                side_effect_hash=None,
                error="stub failure",
            )
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
class ProxyTracesEndpointTest(unittest.TestCase):
    def _build(self, *, debug: bool) -> TestClient:
        tmp = Path(self._tmp.name)
        if debug:
            os.environ["INSPECT_IA_AGENTS_PROXY_DEBUG"] = "on"
        else:
            os.environ.pop("INSPECT_IA_AGENTS_PROXY_DEBUG", None)
        app = create_app(
            config_store=ConfigStore(tmp / "config.json"),
            event_store=InMemoryEventStore(),
            policy_store=PolicyStore(tmp / "policies"),
            proxy=_StubProxy(),
            catalog=Catalog(SPECS),
        )
        client = TestClient(app)
        resp = client.post(
            "/config/agents",
            json={
                "id": "agent-admin",
                "runtime": "lab",
                "role": "identity_admin",
                "capability_scope": ["okta"],
            },
        )
        self.assertEqual(resp.status_code, 201, resp.text)
        return client

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(lambda: os.environ.pop("INSPECT_IA_AGENTS_PROXY_DEBUG", None))

    def _add_agent(self, client: TestClient, agent_id: str) -> None:
        resp = client.post(
            "/config/agents",
            json={
                "id": agent_id,
                "runtime": "lab",
                "role": "identity_admin",
                "capability_scope": ["okta"],
            },
        )
        self.assertEqual(resp.status_code, 201, resp.text)

    def _execute(
        self,
        client: TestClient,
        *,
        agent_id: str = "agent-admin",
        payload: dict | None = None,
    ):  # type: ignore[no-untyped-def]
        return client.post(
            "/actions/execute",
            json={
                "agent_id": agent_id,
                "action_type": "list_users",
                "target_system": "okta",
                "resource": "org/acme",
                "payload": payload if payload is not None else {"reason": "test"},
            },
        )

    def test_debug_status_reports_enabled(self) -> None:
        client = self._build(debug=True)
        body = client.get("/proxy/debug").json()
        self.assertTrue(body["debug_enabled"])
        self.assertEqual(body["trace_count"], 0)

    def test_executed_side_effect_is_traced_when_debug_on(self) -> None:
        client = self._build(debug=True)
        self.assertEqual(self._execute(client).status_code, 200)
        body = client.get("/proxy/traces").json()
        self.assertTrue(body["debug_enabled"])
        self.assertEqual(len(body["traces"]), 1)
        trace = body["traces"][0]
        self.assertEqual(trace["action_type"], "list_users")
        self.assertEqual(trace["target_system"], "okta")
        self.assertTrue(trace["ok"])
        self.assertIsNotNone(trace["side_effect_hash"])
        self.assertEqual(trace["request_payload"], {"reason": "test"})

    def test_no_trace_recorded_when_debug_off(self) -> None:
        client = self._build(debug=False)
        self.assertEqual(self._execute(client).status_code, 200)
        body = client.get("/proxy/traces").json()
        self.assertFalse(body["debug_enabled"])
        self.assertEqual(body["traces"], [])

    def test_tail_limits_returned_traces(self) -> None:
        client = self._build(debug=True)
        for _ in range(3):
            self._execute(client)
        body = client.get("/proxy/traces", params={"tail": 2}).json()
        self.assertEqual(len(body["traces"]), 2)
        self.assertEqual([t["seq"] for t in body["traces"]], [2, 3])

    def test_delete_clears_buffer(self) -> None:
        client = self._build(debug=True)
        self._execute(client)
        self.assertEqual(client.delete("/proxy/traces").json(), {"cleared": True})
        self.assertEqual(client.get("/proxy/traces").json()["traces"], [])

    # --- Task 6: delta-poll (since_seq) + server-side filters -------------

    def test_tail_only_envelope_stays_backward_compatible(self) -> None:
        # tail-only keeps the historical behavior (last N, ascending) and the
        # old envelope keys; the new cursor keys ride along.
        client = self._build(debug=True)
        for _ in range(3):
            self._execute(client)
        body = client.get("/proxy/traces", params={"tail": 2}).json()
        self.assertTrue(body["debug_enabled"])
        self.assertEqual([t["seq"] for t in body["traces"]], [2, 3])
        self.assertEqual(body["last_seq"], 3)
        self.assertEqual(body["total"], 3)
        self.assertFalse(body["reset"])

    def test_since_seq_returns_delta_only(self) -> None:
        client = self._build(debug=True)
        for _ in range(5):
            self._execute(client)
        body = client.get("/proxy/traces", params={"since_seq": 3}).json()
        self.assertEqual([t["seq"] for t in body["traces"]], [4, 5])
        self.assertEqual(body["last_seq"], 5)
        self.assertEqual(body["total"], 5)
        self.assertFalse(body["reset"])

    def test_agent_id_filter_is_server_side_and_totals_reflect_it(self) -> None:
        client = self._build(debug=True)
        self._add_agent(client, "agent-two")
        self._execute(client)
        self._execute(client, agent_id="agent-two")
        self._execute(client)
        body = client.get("/proxy/traces", params={"agent_id": "agent-two"}).json()
        self.assertEqual([t["agent_id"] for t in body["traces"]], ["agent-two"])
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["last_seq"], 3)  # cursor stays unfiltered

    def test_outcome_fail_returns_only_failures(self) -> None:
        client = self._build(debug=True)
        self._execute(client)
        self._execute(client, payload={"reason": "boom", "fail": True})
        body = client.get("/proxy/traces", params={"outcome": "fail"}).json()
        self.assertEqual(len(body["traces"]), 1)
        self.assertFalse(body["traces"][0]["ok"])
        self.assertEqual(body["total"], 1)

    def test_outcome_garbage_is_422(self) -> None:
        client = self._build(debug=True)
        resp = client.get("/proxy/traces", params={"outcome": "garbage"})
        self.assertEqual(resp.status_code, 422)

    def test_q_substring_matches_payload(self) -> None:
        client = self._build(debug=True)
        self._execute(client, payload={"reason": "needle-xyz"})
        self._execute(client)
        body = client.get("/proxy/traces", params={"q": "needle-xyz"}).json()
        self.assertEqual(len(body["traces"]), 1)
        self.assertEqual(body["traces"][0]["request_payload"], {"reason": "needle-xyz"})
        self.assertEqual(body["total"], 1)

    def test_limit_returns_first_n_ascending(self) -> None:
        client = self._build(debug=True)
        for _ in range(4):
            self._execute(client)
        body = client.get("/proxy/traces", params={"limit": 2}).json()
        self.assertEqual([t["seq"] for t in body["traces"]], [1, 2])
        self.assertEqual(body["last_seq"], 4)
        self.assertEqual(body["total"], 4)

    def test_reset_when_cursor_is_ahead_of_server(self) -> None:
        # A since_seq beyond MAX(seq) means the client cursor survived a
        # clear/restart: the server flags reset and serves the full selection.
        client = self._build(debug=True)
        for _ in range(3):
            self._execute(client)
        body = client.get("/proxy/traces", params={"since_seq": 999}).json()
        self.assertTrue(body["reset"])
        self.assertEqual([t["seq"] for t in body["traces"]], [1, 2, 3])
        self.assertEqual(body["last_seq"], 3)
        self.assertEqual(body["total"], 3)

    def test_filtered_view_is_still_redacted(self) -> None:
        # The query path emits through _redacted_view like the legacy path:
        # a Bearer credential in the payload is masked in the VIEW only.
        secret = "secrettoken" + "123"
        client = self._build(debug=True)
        self._execute(client, payload={"reason": f"Bearer {secret}"})
        body = client.get("/proxy/traces", params={"since_seq": 0}).json()
        self.assertEqual(len(body["traces"]), 1)
        payload_text = str(body["traces"][0]["request_payload"])
        self.assertNotIn(secret, payload_text)
        self.assertIn("***REDACTED***", payload_text)


if __name__ == "__main__":
    unittest.main()
