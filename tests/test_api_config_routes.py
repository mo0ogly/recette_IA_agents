"""U1/U4: config CRUD over HTTP."""

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
class TestConfigRoutes(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        store = ConfigStore(Path(self.tmp.name) / "cfg.json")
        self.client = TestClient(create_app(config_store=store))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_ai_backend_crud(self) -> None:
        self.assertEqual(self.client.get("/config/ai-backends").json(), [])
        r = self.client.post(
            "/config/ai-backends",
            json={"id": "b1", "provider": "anthropic", "model": "claude"},
        )
        self.assertEqual(r.status_code, 201)
        self.assertEqual(len(self.client.get("/config/ai-backends").json()), 1)
        self.assertEqual(self.client.delete("/config/ai-backends/b1").status_code, 204)

    def test_post_secret_rejected_400(self) -> None:
        r = self.client.post(
            "/config/ai-backends",
            json={"id": "b", "provider": "openai", "model": "x", "api_key": "leak"},
        )
        self.assertEqual(r.status_code, 400)

    def test_agent_crud_and_404(self) -> None:
        self.client.post(
            "/config/ai-backends",
            json={"id": "b1", "provider": "anthropic", "model": "c"},
        )
        r = self.client.post(
            "/config/agents",
            json={
                "id": "a1",
                "principal": "p",
                "target_system": "github",
                "goal": "g",
                "capability_scope": ["read_repo"],
                "ai_backend_id": "b1",
                "runtime": "lab",
            },
        )
        self.assertEqual(r.status_code, 201)
        r = self.client.put("/config/agents/a1", json={"goal": "g2"})
        self.assertEqual(r.json()["goal"], "g2")
        self.assertEqual(
            self.client.put("/config/agents/nope", json={"goal": "x"}).status_code, 404
        )
        self.assertEqual(self.client.delete("/config/agents/a1").status_code, 204)

    def test_servers_list_empty(self) -> None:
        self.assertEqual(self.client.get("/config/servers").json(), [])

    def test_server_create_and_roundtrip(self) -> None:
        server = {"id": "s1", "system": "github", "mode": "mock_local", "port": 8081}
        r = self.client.post("/config/servers", json=server)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json(), server)
        self.assertEqual(self.client.get("/config/servers").json(), [server])

    def test_server_duplicate_id_is_400(self) -> None:
        server = {"id": "s1", "system": "github", "mode": "mock_local", "port": 8081}
        self.client.post("/config/servers", json=server)
        r = self.client.post("/config/servers", json=server)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(len(self.client.get("/config/servers").json()), 1)

    def test_server_invalid_mode_is_400(self) -> None:
        r = self.client.post(
            "/config/servers",
            json={"id": "s1", "system": "github", "mode": "bogus"},
        )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.client.get("/config/servers").json(), [])

    def test_server_update_persists(self) -> None:
        self.client.post(
            "/config/servers",
            json={"id": "s1", "system": "github", "mode": "mock_local", "port": 8081},
        )
        r = self.client.put("/config/servers/s1", json={"port": 9090})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["port"], 9090)
        self.assertEqual(self.client.get("/config/servers").json()[0]["port"], 9090)

    def test_server_update_unknown_is_404(self) -> None:
        r = self.client.put("/config/servers/nope", json={"port": 1})
        self.assertEqual(r.status_code, 404)

    def test_server_update_bad_mode_is_400_not_404(self) -> None:
        self.client.post(
            "/config/servers",
            json={"id": "s1", "system": "github", "mode": "mock_local", "port": 8081},
        )
        r = self.client.put("/config/servers/s1", json={"mode": "bogus"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(
            self.client.get("/config/servers").json()[0]["mode"], "mock_local"
        )

    def test_server_delete_then_gone(self) -> None:
        self.client.post(
            "/config/servers",
            json={"id": "s1", "system": "github", "mode": "mock_local", "port": 8081},
        )
        self.assertEqual(self.client.delete("/config/servers/s1").status_code, 204)
        self.assertEqual(self.client.get("/config/servers").json(), [])

    def test_server_delete_unknown_is_404(self) -> None:
        self.assertEqual(self.client.delete("/config/servers/nope").status_code, 404)

    def test_update_bad_runtime_is_400_not_404(self) -> None:
        self.client.post(
            "/config/agents",
            json={
                "id": "a1",
                "principal": "p",
                "target_system": "github",
                "goal": "g",
                "capability_scope": [],
                "ai_backend_id": "b1",
                "runtime": "lab",
            },
        )
        r = self.client.put("/config/agents/a1", json={"runtime": "bogus"})
        self.assertEqual(r.status_code, 400)
