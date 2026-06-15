"""Endpoint test for GET /proxy/reconcile (wire-vs-audit, allowlist slice).

Container-free: seed the wire recorder via POST /proxy/wire with one allowlisted
flow (the lab) and one honeypot flow (:9113), then assert /proxy/reconcile flags
the honeypot as a bypass. The deterministic recette never runs a real overlay.
"""

from __future__ import annotations

import unittest

try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover - depends on the [api] extra
    _HAS_FASTAPI = False


def _flow(**over: object) -> dict:
    base = {
        "method": "POST",
        "scheme": "http",
        "host": "127.0.0.1",
        "port": 8082,
        "path": "/github/execute",
        "status_code": 200,
        "request_body": "{}",
        "response_body": "{}",
        "run_id": "run-1",
    }
    base.update(over)
    return base


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class ReconcileEndpointTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_clean_run_reconciles_ok(self) -> None:
        # A single flow to the lab (:8082) -> mediated -> ok.
        self.client.post("/proxy/wire", json=_flow(port=8082))
        body = self.client.get("/proxy/reconcile", params={"run_id": "run-1"}).json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["bypass_flows"], [])

    def test_honeypot_flow_is_flagged_as_bypass(self) -> None:
        self.client.post("/proxy/wire", json=_flow(port=8082))  # lab, allowed
        self.client.post("/proxy/wire", json=_flow(port=9113, path="/write"))  # honeypot
        body = self.client.get("/proxy/reconcile", params={"run_id": "run-1"}).json()
        self.assertFalse(body["ok"])
        self.assertEqual([f["port"] for f in body["bypass_flows"]], [9113])


if __name__ == "__main__":
    unittest.main()
