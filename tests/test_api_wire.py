"""Endpoint tests for the wire overlay (/proxy/wire*).

Container-free: the endpoints are exercised through the in-memory recorder, so
ingest -> list -> clear and the status contract are verified without a live
mitmproxy. The deterministic recette never enables the overlay; these tests only
assert the API surface the addon and the console rely on.
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
class WireEndpointsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_status_off_by_default(self) -> None:
        body = self.client.get("/proxy/wire/status").json()
        # No INSPECT_IA_AGENTS_WIRE_PROXY in the test env -> overlay reports disabled.
        self.assertFalse(body["enabled"])
        self.assertIsNone(body["proxy_url"])
        self.assertEqual(body["flow_count"], 0)

    def test_ingest_then_list(self) -> None:
        r = self.client.post("/proxy/wire", json=_flow())
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["seq"], 1)

        body = self.client.get("/proxy/wire").json()
        self.assertEqual(len(body["flows"]), 1)
        flow = body["flows"][0]
        self.assertEqual(flow["method"], "POST")
        self.assertEqual(flow["host"], "localhost")
        self.assertTrue(flow["ok"])

    def test_ingest_orders_by_seq_and_tail_trims(self) -> None:
        for p in ("/a", "/b", "/c"):
            self.client.post("/proxy/wire", json=_flow(path=p))
        flows = self.client.get("/proxy/wire", params={"tail": 2}).json()["flows"]
        self.assertEqual([f["path"] for f in flows], ["/b", "/c"])

    def test_run_id_filter(self) -> None:
        self.client.post("/proxy/wire", json=_flow(run_id="run-1"))
        self.client.post("/proxy/wire", json=_flow(run_id="run-2"))
        flows = self.client.get("/proxy/wire", params={"run_id": "run-2"}).json()["flows"]
        self.assertEqual(len(flows), 1)
        self.assertEqual(flows[0]["run_id"], "run-2")

    def test_malformed_payload_is_422(self) -> None:
        # A JSON array is not a flow object -> validated, not trusted.
        r = self.client.post("/proxy/wire", json=["nope"])
        self.assertEqual(r.status_code, 422)

    def test_clear_empties_the_buffer(self) -> None:
        self.client.post("/proxy/wire", json=_flow())
        self.assertEqual(self.client.delete("/proxy/wire").json(), {"cleared": True})
        self.assertEqual(self.client.get("/proxy/wire").json()["flows"], [])

    def test_failed_flow_not_ok(self) -> None:
        self.client.post("/proxy/wire", json=_flow(status_code=500))
        flow = self.client.get("/proxy/wire").json()["flows"][0]
        self.assertFalse(flow["ok"])


if __name__ == "__main__":
    unittest.main()
