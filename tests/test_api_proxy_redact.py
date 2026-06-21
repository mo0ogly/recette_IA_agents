"""Endpoint-level redaction tests for the console-facing proxy views.

Container-free: a wire flow carrying a secret is ingested through the in-memory
recorder, then GET /proxy/wire is asserted to mask the secret while preserving
the ``side_effect_hash`` integrity value. The audit log / recorder objects are
never touched -- only the emitted VIEW is redacted (I1).
"""

from __future__ import annotations

import unittest
from unittest import mock

try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app
    from recette.api.routers.proxy import _redacted_view

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover - depends on the [api] extra
    _HAS_FASTAPI = False

_SECRET = "secrettoken" + "123"


def _flow_with_secret(**over: object) -> dict:
    base = {
        "method": "POST",
        "scheme": "http",
        "host": "localhost",
        "port": 8082,
        "path": "/github/execute",
        "status_code": 200,
        "content_type": "application/json",
        "request_body": f"Authorization: Bearer {_SECRET}",
        "response_body": '{"success":true}',
    }
    base.update(over)
    return base


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class ProxyRedactEndpointTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_wire_view_masks_secret_keeps_hash(self) -> None:
        r = self.client.post("/proxy/wire", json=_flow_with_secret())
        self.assertEqual(r.status_code, 201)

        body = self.client.get("/proxy/wire").json()
        self.assertEqual(len(body["flows"]), 1)
        flow = body["flows"][0]
        # The secret is masked in the emitted body.
        self.assertNotIn(_SECRET, flow["request_body"])
        self.assertIn("***REDACTED***", flow["request_body"])
        # The integrity hash field is still present (preserved verbatim, I1).
        self.assertIn("side_effect_hash", flow)

    def test_redact_off_leaks_secret(self) -> None:
        self.client.post("/proxy/wire", json=_flow_with_secret())
        with mock.patch.dict("os.environ", {"INSPECT_IA_AGENTS_PROXY_REDACT": "off"}):
            body = self.client.get("/proxy/wire").json()
        self.assertIn(_SECRET, body["flows"][0]["request_body"])

    def test_traces_view_redacts_and_keeps_hash(self) -> None:
        # The /proxy/traces view is driven by the proxy_trace_recorder, which is
        # populated only by real side-effect execution (no API to plant a trace
        # directly). The endpoint maps each ProxyTrace through _redacted_view, so
        # this asserts that helper redacts a trace-shaped dict while preserving
        # the side_effect_hash integrity value verbatim (I1) -- the exact contract
        # GET /proxy/traces relies on.
        trace = {
            "seq": 1,
            "event_id": "01J0",
            "timestamp": "1970-01-01T00:00:00Z",
            "agent_id": "agent-1",
            "target_system": "github",
            "target": "api.github.com",
            "action_type": "open_issue",
            "resource": "/repos/x/y/issues",
            "request_payload": {"authorization": f"Bearer {_SECRET}"},
            "ok": True,
            "status_code": 200,
            "side_effect_hash": "deadbeefcafef00d",
            "error": None,
            "run_id": "run-1",
            "response": {"note": f"token: {_SECRET}"},
        }
        out = _redacted_view(trace)
        self.assertNotIn(_SECRET, str(out["request_payload"]))
        self.assertNotIn(_SECRET, str(out["response"]))
        self.assertIn("***REDACTED***", str(out["request_payload"]))
        # The integrity hash is preserved verbatim (never redacted).
        self.assertEqual(out["side_effect_hash"], "deadbeefcafef00d")


if __name__ == "__main__":
    unittest.main()
