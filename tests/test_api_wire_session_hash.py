import unittest

try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover - depends on the [api] extra
    _HAS_FASTAPI = False


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class WireFlowHashTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_governed_flow_carries_recomputed_side_effect_hash(self) -> None:
        flow = {
            "method": "POST",
            "scheme": "http",
            "host": "127.0.0.1",
            "port": 9101,
            "path": "/github/execute",
            "status_code": 200,
            "content_type": "application/json",
            "request_body": (
                '{"event_id":"e1","action_type":"read_repo","resource":"acme/x","payload":{}}'
            ),
            "response_body": ('{"data":{"action":"read_repo","resource":"acme/x"},"success":true}'),
            "run_id": "RUN-1",
        }
        r = self.client.post("/proxy/wire", json=flow)
        self.assertEqual(r.status_code, 201)
        listed = self.client.get("/proxy/wire").json()["flows"]
        self.assertTrue(listed, "no flow recorded")
        self.assertIn("side_effect_hash", listed[-1])
        self.assertIsInstance(listed[-1]["side_effect_hash"], str)

    def test_non_governed_flow_has_null_hash(self) -> None:
        flow = {
            "method": "GET",
            "scheme": "http",
            "host": "example.com",
            "port": 80,
            "path": "/",
            "status_code": 200,
            "content_type": "text/html",
            "request_body": "",
            "response_body": "<html></html>",
            "run_id": None,
        }
        r = self.client.post("/proxy/wire", json=flow)
        self.assertEqual(r.status_code, 201)
        listed = self.client.get("/proxy/wire").json()["flows"]
        self.assertIn("side_effect_hash", listed[-1])
        self.assertIsNone(listed[-1]["side_effect_hash"])


if __name__ == "__main__":
    unittest.main()
