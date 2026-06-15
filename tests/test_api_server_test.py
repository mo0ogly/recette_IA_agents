"""POST /config/servers/{id}/test -- diagnostic probe against a live server.

Boots the real lab ThreadingHTTPServer in-process on an ephemeral port, points
a mock_local registry entry at it, and drives the endpoint through TestClient.
The endpoint makes a real outbound HTTP call to that server (the I5 proxy path),
so these tests prove the server "answers like a real server" end to end.

Fail-safe is asserted explicitly: a known system + bad action, and a server
that is down, both map to {"ok": false, ...} (never a 500); only an unknown
server id is a 404 and a non-probeable mode (real_saas) is a 400.
"""

from __future__ import annotations

import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

try:
    from fastapi.testclient import TestClient

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover - depends on the [api] extra
    _HAS_FASTAPI = False

from recette.lab.mock_server import _Handler

if _HAS_FASTAPI:
    from recette.api.app import create_app
    from recette.api.config_store import ConfigStore


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class ServerTestEndpointTest(unittest.TestCase):
    def setUp(self) -> None:
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self._tmp = TemporaryDirectory()
        store = ConfigStore(Path(self._tmp.name) / "config.json")
        store.add_server(
            {"id": "okta-up", "system": "okta", "mode": "mock_local", "port": self.port}
        )
        # A mock_local entry whose port has nothing listening: the probe must
        # fail-safe to ok=False, not raise.
        store.add_server({"id": "okta-down", "system": "okta", "mode": "mock_local", "port": 1})
        store.add_server({"id": "saas", "system": "okta", "mode": "real_saas", "owner": "acme"})
        # A declared_url entry pointing at the same live server: it must speak
        # the lab wire format, so the probe succeeds exactly like mock_local.
        store.add_server(
            {
                "id": "okta-declared",
                "system": "okta",
                "mode": "declared_url",
                "base_url": f"http://127.0.0.1:{self.port}",
            }
        )
        self.client = TestClient(create_app(config_store=store))

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self._tmp.cleanup()

    def test_live_server_answers_like_a_real_server(self) -> None:
        res = self.client.post(
            "/config/servers/okta-up/test",
            json={"action_type": "suspend_user", "resource": "user/alice"},
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["status_code"], 200)
        self.assertEqual(body["response"]["status"], "SUSPENDED")
        self.assertEqual(body["response"]["action"], "suspend_user")
        self.assertTrue(body["side_effect_hash"])
        self.assertIsNone(body["error"])

    def test_unknown_action_is_fail_safe_not_a_500(self) -> None:
        res = self.client.post(
            "/config/servers/okta-up/test",
            json={"action_type": "definitely_not_an_action", "resource": "x"},
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertFalse(body["ok"])
        self.assertEqual(body["status_code"], 404)
        self.assertIn("404", body["error"])

    def test_down_server_is_fail_safe(self) -> None:
        res = self.client.post(
            "/config/servers/okta-down/test",
            json={"action_type": "suspend_user", "resource": "user/alice"},
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertFalse(body["ok"])
        self.assertEqual(body["status_code"], 0)
        self.assertIn("unreachable", body["error"])

    def test_missing_action_type_is_400(self) -> None:
        res = self.client.post("/config/servers/okta-up/test", json={"resource": "x"})
        self.assertEqual(res.status_code, 400)
        self.assertIn("action_type", res.json()["detail"])

    def test_unknown_server_is_404(self) -> None:
        res = self.client.post("/config/servers/nope/test", json={"action_type": "suspend_user"})
        self.assertEqual(res.status_code, 404)

    def test_real_saas_cannot_be_probed_is_400(self) -> None:
        res = self.client.post("/config/servers/saas/test", json={"action_type": "suspend_user"})
        self.assertEqual(res.status_code, 400)
        self.assertIn("real_saas", res.json()["detail"])

    def test_declared_url_mode_probes_the_base_url(self) -> None:
        res = self.client.post(
            "/config/servers/okta-declared/test",
            json={"action_type": "suspend_user", "resource": "user/bob"},
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["response"]["status"], "SUSPENDED")

    def test_resource_and_payload_are_forwarded_to_the_server(self) -> None:
        # The resource is echoed back, proving it reached the handler; two
        # distinct payloads yield distinct side_effect_hashes, proving the
        # payload is forwarded (the hash is computed over the response).
        res = self.client.post(
            "/config/servers/okta-up/test",
            json={"action_type": "suspend_user", "resource": "user/carol", "payload": {"a": 1}},
        )
        body = res.json()
        self.assertEqual(body["response"]["resource"], "user/carol")
        first_hash = body["side_effect_hash"]
        res2 = self.client.post(
            "/config/servers/okta-up/test",
            json={"action_type": "list_users", "resource": "org/acme", "payload": {"a": 2}},
        )
        self.assertNotEqual(res2.json()["side_effect_hash"], first_hash)


if __name__ == "__main__":
    unittest.main()
