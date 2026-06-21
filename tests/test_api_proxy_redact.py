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

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover - depends on the [api] extra
    _HAS_FASTAPI = False

_SECRET = "secrettoken123"


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


if __name__ == "__main__":
    unittest.main()
