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

    # --- Task 7: delta-poll (since_seq) + server-side filters -------------

    def test_tail_only_envelope_stays_backward_compatible(self) -> None:
        # tail-only keeps the historical behavior (last N, ascending) and the
        # old envelope keys (enabled/proxy_url/flows); the cursor keys ride along.
        for p in ("/a", "/b", "/c"):
            self.client.post("/proxy/wire", json=_flow(path=p))
        body = self.client.get("/proxy/wire", params={"tail": 2}).json()
        self.assertFalse(body["enabled"])
        self.assertIsNone(body["proxy_url"])
        self.assertEqual([f["path"] for f in body["flows"]], ["/b", "/c"])
        self.assertEqual(body["last_seq"], 3)
        self.assertEqual(body["total"], 3)
        self.assertFalse(body["reset"])

    def test_since_seq_returns_delta_only(self) -> None:
        for i in range(5):
            self.client.post("/proxy/wire", json=_flow(path=f"/p{i}"))
        body = self.client.get("/proxy/wire", params={"since_seq": 3}).json()
        self.assertEqual([f["seq"] for f in body["flows"]], [4, 5])
        self.assertEqual(body["last_seq"], 5)
        self.assertEqual(body["total"], 5)
        self.assertFalse(body["reset"])

    def test_host_filter_is_server_side_and_totals_reflect_it(self) -> None:
        self.client.post("/proxy/wire", json=_flow(host="a.example"))
        self.client.post("/proxy/wire", json=_flow(host="b.example"))
        self.client.post("/proxy/wire", json=_flow(host="a.example"))
        body = self.client.get("/proxy/wire", params={"host": "b.example"}).json()
        self.assertEqual([f["host"] for f in body["flows"]], ["b.example"])
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["last_seq"], 3)  # cursor stays unfiltered

    def test_method_filter_input_is_case_insensitive(self) -> None:
        # The store compares uppercased (the column is normalized uppercase),
        # so a lowercase operator input still matches.
        self.client.post("/proxy/wire", json=_flow(method="GET", path="/read"))
        self.client.post("/proxy/wire", json=_flow(method="POST", path="/write"))
        body = self.client.get("/proxy/wire", params={"method": "post"}).json()
        self.assertEqual([f["method"] for f in body["flows"]], ["POST"])
        self.assertEqual(body["total"], 1)

    def test_status_filter_is_exact(self) -> None:
        self.client.post("/proxy/wire", json=_flow(status_code=200))
        self.client.post("/proxy/wire", json=_flow(status_code=500))
        body = self.client.get("/proxy/wire", params={"status": 500}).json()
        self.assertEqual(len(body["flows"]), 1)
        self.assertEqual(body["flows"][0]["status_code"], 500)
        self.assertFalse(body["flows"][0]["ok"])
        self.assertEqual(body["total"], 1)

    def test_q_substring_matches_path_and_bodies(self) -> None:
        self.client.post("/proxy/wire", json=_flow(path="/needle-xyz/execute"))
        self.client.post("/proxy/wire", json=_flow(response_body='{"marker":"haystack-abc"}'))
        self.client.post("/proxy/wire", json=_flow())
        by_path = self.client.get("/proxy/wire", params={"q": "needle-xyz"}).json()
        self.assertEqual([f["path"] for f in by_path["flows"]], ["/needle-xyz/execute"])
        self.assertEqual(by_path["total"], 1)
        by_body = self.client.get("/proxy/wire", params={"q": "haystack-abc"}).json()
        self.assertEqual(len(by_body["flows"]), 1)
        self.assertIn("haystack-abc", by_body["flows"][0]["response_body"])
        self.assertEqual(by_body["total"], 1)

    def test_limit_returns_first_n_ascending_and_tail_wins(self) -> None:
        for i in range(4):
            self.client.post("/proxy/wire", json=_flow(path=f"/p{i}"))
        body = self.client.get("/proxy/wire", params={"limit": 2}).json()
        self.assertEqual([f["seq"] for f in body["flows"]], [1, 2])
        self.assertEqual(body["last_seq"], 4)
        self.assertEqual(body["total"], 4)
        # Compat: tail wins over limit (last N of the filtered set).
        both = self.client.get("/proxy/wire", params={"limit": 2, "tail": 3}).json()
        self.assertEqual([f["seq"] for f in both["flows"]], [2, 3, 4])

    def test_reset_when_cursor_is_ahead_of_server(self) -> None:
        # A since_seq beyond MAX(seq) means the client cursor survived a
        # clear/restart: the server flags reset and serves the full selection.
        for p in ("/a", "/b", "/c"):
            self.client.post("/proxy/wire", json=_flow(path=p))
        body = self.client.get("/proxy/wire", params={"since_seq": 999}).json()
        self.assertTrue(body["reset"])
        self.assertEqual([f["seq"] for f in body["flows"]], [1, 2, 3])
        self.assertEqual(body["last_seq"], 3)
        self.assertEqual(body["total"], 3)

    def test_query_path_serves_persisted_side_effect_hash(self) -> None:
        # Governed-shaped ingest (event_id + success envelope) carries the
        # persisted side_effect_hash through the query path, like snapshot did.
        governed = _flow(
            request_body=(
                '{"event_id":"e1","action_type":"read_repo","resource":"acme/x","payload":{}}'
            ),
            response_body='{"data":{"action":"read_repo","resource":"acme/x"},"success":true}',
            run_id="RUN-1",
        )
        self.client.post("/proxy/wire", json=governed)
        body = self.client.get("/proxy/wire", params={"since_seq": 0}).json()
        self.assertEqual(len(body["flows"]), 1)
        self.assertIsInstance(body["flows"][0]["side_effect_hash"], str)

    def test_filtered_view_is_still_redacted(self) -> None:
        # The query path emits through _redacted_view like the legacy path:
        # a Bearer credential in the body is masked in the VIEW only.
        secret = "secrettoken" + "123"
        self.client.post("/proxy/wire", json=_flow(request_body=f"Bearer {secret}"))
        body = self.client.get("/proxy/wire", params={"since_seq": 0}).json()
        self.assertEqual(len(body["flows"]), 1)
        self.assertNotIn(secret, body["flows"][0]["request_body"])
        self.assertIn("***REDACTED***", body["flows"][0]["request_body"])

    def test_status_flow_count_uses_store_count(self) -> None:
        # flow_count comes from COUNT(*) now, not a full snapshot rebuild.
        for p in ("/a", "/b", "/c"):
            self.client.post("/proxy/wire", json=_flow(path=p))
        self.assertEqual(self.client.get("/proxy/wire/status").json()["flow_count"], 3)
        self.client.delete("/proxy/wire")
        self.assertEqual(self.client.get("/proxy/wire/status").json()["flow_count"], 0)


if __name__ == "__main__":
    unittest.main()
