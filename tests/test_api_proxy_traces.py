# tests/test_api_proxy_traces.py
"""S5: GET /proxy/traces exposes the debug trace ring (I5 observability).

With AGENTRAIL_PROXY_DEBUG on, the gateway's TracingProxy records each executed
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
from recette.platform.catalog.model import ActionSpec, RiskLevel
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
        verdict_privileged=PolicyVerdict.ALLOW,
        verdict_default=PolicyVerdict.DENY,
        privileged_roles=("identity_admin",),
        description="List users (read-only)",
    ),
)


class _StubProxy:
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


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class ProxyTracesEndpointTest(unittest.TestCase):
    def _build(self, *, debug: bool) -> TestClient:
        tmp = Path(self._tmp.name)
        if debug:
            os.environ["AGENTRAIL_PROXY_DEBUG"] = "on"
        else:
            os.environ.pop("AGENTRAIL_PROXY_DEBUG", None)
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
        self.addCleanup(lambda: os.environ.pop("AGENTRAIL_PROXY_DEBUG", None))

    def _execute(self, client: TestClient):  # type: ignore[no-untyped-def]
        return client.post(
            "/actions/execute",
            json={
                "agent_id": "agent-admin",
                "action_type": "list_users",
                "target_system": "okta",
                "resource": "org/acme",
                "payload": {"reason": "test"},
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


if __name__ == "__main__":
    unittest.main()
