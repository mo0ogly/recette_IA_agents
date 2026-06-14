"""Endpoint tests for the proxy-route selector (/proxy/route)."""

from __future__ import annotations

import unittest

try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover - depends on the [api] extra
    _HAS_FASTAPI = False


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class ProxyRouteEndpointsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_get_lists_targets_and_active(self) -> None:
        body = self.client.get("/proxy/route").json()
        ids = {t["id"] for t in body["targets"]}
        self.assertEqual(ids, {"direct", "wire"})
        # No INSPECT_IA_AGENTS_WIRE_PROXY in the test env -> starts direct.
        self.assertEqual(body["active"], "direct")

    def test_post_switches_active(self) -> None:
        r = self.client.post("/proxy/route", json={"target": "wire"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["active"], "wire")
        self.assertEqual(self.client.get("/proxy/route").json()["active"], "wire")

    def test_post_back_to_direct(self) -> None:
        self.client.post("/proxy/route", json={"target": "wire"})
        self.client.post("/proxy/route", json={"target": "direct"})
        body = self.client.get("/proxy/route").json()
        self.assertEqual(body["active"], "direct")

    def test_unknown_target_is_422(self) -> None:
        r = self.client.post("/proxy/route", json={"target": "nope"})
        self.assertEqual(r.status_code, 422)

    def test_missing_target_is_422(self) -> None:
        r = self.client.post("/proxy/route", json={})
        self.assertEqual(r.status_code, 422)


if __name__ == "__main__":
    unittest.main()
