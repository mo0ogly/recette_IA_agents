"""Task 7: server fqdn/aliases over HTTP (422 on netname collision), the global
containment flag get/set, and the POST /config/resolve name probe.

The config router returns raw dicts (no {success, data} envelope), so these
assertions read the body shape directly, matching the other /config endpoints.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app
    from recette.api.config_store import ConfigStore

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover
    _HAS_FASTAPI = False


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class TestServerNetnameRoutes(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        store = ConfigStore(Path(self.tmp.name) / "cfg.json")
        self.client = TestClient(create_app(config_store=store))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_create_server_with_fqdn_and_aliases_persists(self) -> None:
        server = {
            "id": "s1",
            "system": "github",
            "mode": "mock_local",
            "port": 8081,
            "fqdn": "github.lab.internal",
            "aliases": ["gh.lab.internal", "git.lab.internal"],
        }
        r = self.client.post("/config/servers", json=server)
        self.assertEqual(r.status_code, 201)
        listed = self.client.get("/config/servers").json()
        self.assertEqual(listed[0]["fqdn"], "github.lab.internal")
        self.assertEqual(listed[0]["aliases"], ["gh.lab.internal", "git.lab.internal"])

    def test_create_server_duplicate_fqdn_is_422(self) -> None:
        first = {
            "id": "s1",
            "system": "github",
            "mode": "mock_local",
            "port": 8081,
            "fqdn": "github.lab.internal",
        }
        self.assertEqual(self.client.post("/config/servers", json=first).status_code, 201)
        second = {
            "id": "s2",
            "system": "github",
            "mode": "mock_local",
            "port": 8082,
            "fqdn": "github.lab.internal",
        }
        r = self.client.post("/config/servers", json=second)
        self.assertEqual(r.status_code, 422)
        # The colliding server was not persisted.
        ids = [s["id"] for s in self.client.get("/config/servers").json()]
        self.assertEqual(ids, ["s1"])

    def test_create_server_invalid_hostname_is_422(self) -> None:
        bad = {
            "id": "s1",
            "system": "github",
            "mode": "mock_local",
            "port": 8081,
            "fqdn": "NOT a hostname",
        }
        r = self.client.post("/config/servers", json=bad)
        self.assertEqual(r.status_code, 422)

    def test_duplicate_server_id_is_still_400(self) -> None:
        # Regression: a duplicate id stays a 400 (bad input), distinct from the
        # 422 netname collision.
        server = {"id": "s1", "system": "github", "mode": "mock_local", "port": 8081}
        self.assertEqual(self.client.post("/config/servers", json=server).status_code, 201)
        self.assertEqual(self.client.post("/config/servers", json=server).status_code, 400)


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class TestContainmentFlagRoutes(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ConfigStore(Path(self.tmp.name) / "cfg.json")
        self.client = TestClient(create_app(config_store=self.store))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_get_default_false(self) -> None:
        r = self.client.get("/config/containment")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"containment": False})

    def test_put_true_persists(self) -> None:
        r = self.client.put("/config/containment", json={"enabled": True})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"containment": True})
        # Persisted to disk + readable via the store + the GET endpoint.
        self.assertTrue(self.store.containment_enabled())
        self.assertEqual(self.client.get("/config/containment").json(), {"containment": True})

    def test_put_false_persists(self) -> None:
        self.client.put("/config/containment", json={"enabled": True})
        r = self.client.put("/config/containment", json={"enabled": False})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"containment": False})
        self.assertFalse(self.store.containment_enabled())

    def test_put_missing_enabled_is_422(self) -> None:
        r = self.client.put("/config/containment", json={})
        self.assertEqual(r.status_code, 422)


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class TestResolveProbeRoute(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ConfigStore(Path(self.tmp.name) / "cfg.json")
        self.client = TestClient(create_app(config_store=self.store))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _add_named_server(self) -> None:
        r = self.client.post(
            "/config/servers",
            json={
                "id": "s1",
                "system": "github",
                "mode": "mock_local",
                "port": 8081,
                "fqdn": "github.lab.internal",
                "aliases": ["gh.lab.internal"],
            },
        )
        self.assertEqual(r.status_code, 201)

    def test_resolve_declared_fqdn_resolves(self) -> None:
        self._add_named_server()
        r = self.client.post("/config/resolve", json={"name": "github.lab.internal"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            r.json(),
            {
                "name": "github.lab.internal",
                "resolved": True,
                "server_id": "s1",
                "fqdn": "github.lab.internal",
            },
        )

    def test_resolve_alias_resolves(self) -> None:
        self._add_named_server()
        r = self.client.post("/config/resolve", json={"name": "gh.lab.internal"})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["resolved"])
        self.assertEqual(body["server_id"], "s1")

    def test_resolve_unknown_containment_true_is_not_in_allowlist(self) -> None:
        self._add_named_server()
        r = self.client.post(
            "/config/resolve",
            json={"name": "evil.example.com", "containment": True},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            r.json(),
            {"name": "evil.example.com", "resolved": False, "reason": "not_in_allowlist"},
        )

    def test_resolve_unknown_containment_false_is_unknown_legacy(self) -> None:
        self._add_named_server()
        r = self.client.post(
            "/config/resolve",
            json={"name": "evil.example.com", "containment": False},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            r.json(),
            {"name": "evil.example.com", "resolved": False, "reason": "unknown_legacy"},
        )

    def test_resolve_defaults_containment_to_global_flag(self) -> None:
        # No "containment" in the body -> the store's global flag decides.
        self._add_named_server()
        self.client.put("/config/containment", json={"enabled": True})
        r = self.client.post("/config/resolve", json={"name": "evil.example.com"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["reason"], "not_in_allowlist")

    def test_resolve_missing_name_is_422(self) -> None:
        r = self.client.post("/config/resolve", json={})
        self.assertEqual(r.status_code, 422)


if __name__ == "__main__":
    unittest.main()
