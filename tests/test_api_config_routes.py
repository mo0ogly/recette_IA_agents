"""U1/U4: config CRUD over HTTP. B5: server lifecycle + access-log tail."""

from __future__ import annotations

import http.server
import json
import os
import socket
import tempfile
import threading
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app
    from recette.api.config_store import ConfigStore
    from recette.api.secret_store import BackendSecretStore
    from recette.llm import LlmDecision, StubLlm

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

    def test_ai_providers_catalog_matches_factory(self) -> None:
        from recette.llm import _PROVIDERS

        catalog = self.client.get("/config/ai-providers").json()
        ids = [entry["id"] for entry in catalog]
        # The catalog is the single source for the console dropdown: it must list
        # exactly the providers the llm factory builds, in order.
        self.assertEqual(ids, list(_PROVIDERS))
        by_id = {entry["id"]: entry for entry in catalog}
        # openai_compat needs a base_url and no key; bedrock takes an optional one.
        self.assertEqual(by_id["openai_compat"]["base_url"], "required")
        self.assertFalse(by_id["openai_compat"]["key_required"])
        self.assertIsNone(by_id["openai_compat"]["env_key"])
        self.assertEqual(by_id["bedrock"]["base_url"], "optional")
        self.assertEqual(by_id["moonshot"]["env_key"], "KIMI_API_KEY")
        self.assertTrue(by_id["moonshot"]["key_required"])
        # Each entry carries the curated model dropdown (first = default_model).
        # A provider with curated models exposes them; one without falls back to
        # an empty list + null default (the console then shows a free-text field).
        from recette.llm import provider_models

        for entry in catalog:
            expected = list(provider_models(entry["id"]))
            self.assertEqual(entry["models"], expected)
            self.assertEqual(entry["default_model"], expected[0] if expected else None)
        # mistral is curated: its default is the first listed model, not a model
        # of another provider (regression: the form used to keep a groq model
        # selected after switching to mistral).
        self.assertEqual(by_id["mistral"]["default_model"], "mistral-large-latest")
        self.assertIn("mistral-large-latest", by_id["mistral"]["models"])
        # openai_compat curates none -> empty list + null default (free text).
        self.assertEqual(by_id["openai_compat"]["models"], [])
        self.assertIsNone(by_id["openai_compat"]["default_model"])

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

    def test_agent_delete_unknown_is_404(self) -> None:
        # Strict 404 on unknown id, mirroring the server delete route.
        self.assertEqual(self.client.delete("/config/agents/nope").status_code, 404)

    def test_agent_detail_roundtrip_and_404(self) -> None:
        # Detail-by-id: the console needs a single-agent fetch (a list scan is
        # not a contract). Strict 404 on unknown id, like the delete route.
        self.client.post(
            "/config/agents",
            json={
                "id": "a1",
                "principal": "p",
                "target_system": "github",
                "goal": "g",
                "capability_scope": ["read_repo"],
                "runtime": "lab",
            },
        )
        r = self.client.get("/config/agents/a1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["id"], "a1")
        self.assertEqual(r.json()["goal"], "g")
        self.assertEqual(self.client.get("/config/agents/nope").status_code, 404)

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
        self.assertEqual(self.client.get("/config/servers").json()[0]["mode"], "mock_local")

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


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class TestAiBackendConnectivityProbe(unittest.TestCase):
    """POST /config/ai-backends/{id}/test: diagnostic probe, 200 always (404 on unknown id)."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        store = ConfigStore(Path(self.tmp.name) / "cfg.json")
        secrets = BackendSecretStore(Path(self.tmp.name) / "secrets.json")
        self.app = create_app(config_store=store, secret_store=secrets)
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _add_backend(self, backend: dict) -> None:
        r = self.client.post("/config/ai-backends", json=backend)
        self.assertEqual(r.status_code, 201)

    def test_ok_true_with_stub_factory(self) -> None:
        self._add_backend({"id": "b1", "provider": "anthropic", "model": "claude"})

        def fake_factory(
            provider: str,
            model: str,
            *,
            client: object | None = None,
            base_url: str | None = None,
            api_key: str | None = None,
        ) -> StubLlm:
            return StubLlm([LlmDecision(kind="final", text="pong")])

        self.app.state.llm_factory = fake_factory
        r = self.client.post("/config/ai-backends/b1/test")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["ok"])
        self.assertIsInstance(body["latency_ms"], int)
        self.assertGreaterEqual(body["latency_ms"], 0)
        self.assertEqual(body["kind"], "final")

    def test_factory_receives_stored_secret(self) -> None:
        # A secret set in the store must be threaded into the factory call.
        self._add_backend({"id": "b1", "provider": "anthropic", "model": "claude"})
        self.app.state.secret_store.set_secret("b1", "sk-from-store")
        captured: dict = {}

        def fake_factory(
            provider: str,
            model: str,
            *,
            client: object | None = None,
            base_url: str | None = None,
            api_key: str | None = None,
        ) -> StubLlm:
            captured["api_key"] = api_key
            return StubLlm([LlmDecision(kind="final", text="pong")])

        self.app.state.llm_factory = fake_factory
        r = self.client.post("/config/ai-backends/b1/test")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(captured["api_key"], "sk-from-store")

    def test_factory_api_key_none_when_no_secret(self) -> None:
        # No secret set: api_key is None so the provider env fallback applies.
        self._add_backend({"id": "b1", "provider": "anthropic", "model": "claude"})
        captured: dict = {}

        def fake_factory(
            provider: str,
            model: str,
            *,
            client: object | None = None,
            base_url: str | None = None,
            api_key: str | None = None,
        ) -> StubLlm:
            captured["api_key"] = api_key
            return StubLlm([LlmDecision(kind="final", text="pong")])

        self.app.state.llm_factory = fake_factory
        r = self.client.post("/config/ai-backends/b1/test")
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(captured["api_key"])

    def test_missing_key_is_ok_false_not_500(self) -> None:
        # Default factory (build_llm): constructing GeminiLlm without a key
        # raises RuntimeError -- the probe maps it to ok=false, never a 500.
        self._add_backend({"id": "b1", "provider": "gemini", "model": "m"})
        old = os.environ.pop("GEMINI_API_KEY", None)
        try:
            r = self.client.post("/config/ai-backends/b1/test")
        finally:
            if old is not None:
                os.environ["GEMINI_API_KEY"] = old
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertFalse(body["ok"])
        self.assertIsInstance(body["latency_ms"], int)
        self.assertIn("GEMINI_API_KEY", body["error"])

    def test_unknown_backend_is_404(self) -> None:
        r = self.client.post("/config/ai-backends/nope/test")
        self.assertEqual(r.status_code, 404)

    def test_factory_value_error_is_ok_false(self) -> None:
        # e.g. openai_compat without base_url raises ValueError in build_llm.
        self._add_backend({"id": "b1", "provider": "openai_compat", "model": "m"})
        r = self.client.post("/config/ai-backends/b1/test")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertFalse(body["ok"])
        self.assertIn("openai_compat requires base_url", body["error"])

    def _capturing_factory(self, text: str, captured: dict):
        """A factory whose StubLlm records the history it was asked to decide on."""

        class _CapturingLlm(StubLlm):
            def decide(self, *, system, history, tools):
                captured["system"] = system
                captured["history"] = list(history)
                return super().decide(system=system, history=history, tools=tools)

        def fake_factory(
            provider: str,
            model: str,
            *,
            client: object | None = None,
            base_url: str | None = None,
            api_key: str | None = None,
        ):
            return _CapturingLlm([LlmDecision(kind="final", text=text)])

        return fake_factory

    def test_no_body_returns_text_and_connectivity_default(self) -> None:
        # POST with no body keeps the connectivity probe AND now returns text.
        self._add_backend({"id": "b1", "provider": "anthropic", "model": "claude"})
        captured: dict = {}
        self.app.state.llm_factory = self._capturing_factory("answer-text", captured)
        r = self.client.post("/config/ai-backends/b1/test")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["text"], "answer-text")
        self.assertEqual(body["kind"], "final")
        # Connectivity default user message stays "ping".
        self.assertEqual(captured["history"][-1].content, "ping")

    def test_custom_prompt_is_threaded_and_echoed(self) -> None:
        # A non-empty prompt reaches the llm as the last user message; text echoes back.
        self._add_backend({"id": "b1", "provider": "anthropic", "model": "claude"})
        captured: dict = {}
        self.app.state.llm_factory = self._capturing_factory("the model reply", captured)
        r = self.client.post("/config/ai-backends/b1/test", json={"prompt": "what is 2+2"})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["text"], "the model reply")
        self.assertEqual(captured["history"][-1].content, "what is 2+2")
        self.assertEqual(captured["history"][-1].role, "user")

    def test_empty_prompt_falls_back_to_ping(self) -> None:
        # An empty/whitespace prompt is treated as no prompt: connectivity ping.
        self._add_backend({"id": "b1", "provider": "anthropic", "model": "claude"})
        captured: dict = {}
        self.app.state.llm_factory = self._capturing_factory("x", captured)
        r = self.client.post("/config/ai-backends/b1/test", json={"prompt": "   "})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])
        self.assertEqual(captured["history"][-1].content, "ping")

    def test_prompt_unknown_backend_is_404(self) -> None:
        r = self.client.post("/config/ai-backends/nope/test", json={"prompt": "hi"})
        self.assertEqual(r.status_code, 404)


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class TestAiBackendSecretRoutes(unittest.TestCase):
    """PUT/DELETE /config/ai-backends/{id}/secret + key_configured in listing (R8)."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        store = ConfigStore(Path(self.tmp.name) / "cfg.json")
        self.secrets = BackendSecretStore(Path(self.tmp.name) / "secrets.json")
        self.app = create_app(config_store=store, secret_store=self.secrets)
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _add_backend(self, backend_id: str = "b1", provider: str = "anthropic") -> None:
        r = self.client.post(
            "/config/ai-backends",
            json={"id": backend_id, "provider": provider, "model": "m"},
        )
        self.assertEqual(r.status_code, 201)

    def _backend_entry(self, backend_id: str) -> dict:
        entries = self.client.get("/config/ai-backends").json()
        return next(e for e in entries if e["id"] == backend_id)

    def test_put_sets_secret(self) -> None:
        self._add_backend()
        r = self.client.put("/config/ai-backends/b1/secret", json={"api_key": "sk-xyz"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"configured": True})
        self.assertTrue(self.secrets.is_configured("b1"))
        self.assertTrue(self._backend_entry("b1")["key_configured"])

    def test_put_never_echoes_key(self) -> None:
        self._add_backend()
        r = self.client.put("/config/ai-backends/b1/secret", json={"api_key": "sk-secret-value"})
        self.assertNotIn("sk-secret-value", r.text)

    def test_put_empty_api_key_is_400(self) -> None:
        self._add_backend()
        r = self.client.put("/config/ai-backends/b1/secret", json={"api_key": "  "})
        self.assertEqual(r.status_code, 400)
        self.assertFalse(self.secrets.is_configured("b1"))

    def test_put_missing_api_key_is_400(self) -> None:
        self._add_backend()
        r = self.client.put("/config/ai-backends/b1/secret", json={})
        self.assertEqual(r.status_code, 400)

    def test_put_unknown_backend_is_404(self) -> None:
        r = self.client.put("/config/ai-backends/nope/secret", json={"api_key": "k"})
        self.assertEqual(r.status_code, 404)
        self.assertFalse(self.secrets.is_configured("nope"))

    def test_delete_removes_secret(self) -> None:
        self._add_backend()
        self.client.put("/config/ai-backends/b1/secret", json={"api_key": "k"})
        r = self.client.delete("/config/ai-backends/b1/secret")
        self.assertEqual(r.status_code, 204)
        self.assertFalse(self.secrets.is_configured("b1"))

    def test_delete_unknown_backend_is_404(self) -> None:
        r = self.client.delete("/config/ai-backends/nope/secret")
        self.assertEqual(r.status_code, 404)

    def test_key_configured_reflects_env_fallback(self) -> None:
        # No store secret, but the provider env var present -> key_configured.
        self._add_backend("b1", provider="anthropic")
        old = os.environ.get("ANTHROPIC_API_KEY")
        os.environ["ANTHROPIC_API_KEY"] = "env-key"
        try:
            self.assertTrue(self._backend_entry("b1")["key_configured"])
        finally:
            if old is None:
                os.environ.pop("ANTHROPIC_API_KEY", None)
            else:
                os.environ["ANTHROPIC_API_KEY"] = old

    def test_key_configured_false_without_secret_or_env(self) -> None:
        self._add_backend("b1", provider="anthropic")
        old = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            self.assertFalse(self._backend_entry("b1")["key_configured"])
        finally:
            if old is not None:
                os.environ["ANTHROPIC_API_KEY"] = old

    def test_openai_compat_always_key_configured(self) -> None:
        # openai_compat key is optional (keyless local servers) -> always true.
        self._add_backend("b1", provider="openai_compat")
        self.assertTrue(self._backend_entry("b1")["key_configured"])

    def test_listing_never_contains_key_value(self) -> None:
        self._add_backend()
        self.client.put("/config/ai-backends/b1/secret", json={"api_key": "sk-do-not-leak"})
        r = self.client.get("/config/ai-backends")
        self.assertNotIn("sk-do-not-leak", r.text)


class _FakeServerManager:
    """Test double for app.state.server_manager: records calls, canned results.

    The real ServerManager spawns subprocesses; it is integration-tested in
    tests/test_lab_server_lifecycle.py. Routes only need the call contract.
    """

    def __init__(self, log_path: Path) -> None:
        self._log_path = log_path
        self.calls: list[tuple] = []
        self.start_result: dict = {"status": "up"}
        self.status_result: str = "up"

    def start(self, server: dict) -> dict:
        self.calls.append(("start", server["id"]))
        return self.start_result

    def stop(self, server_id: str) -> dict:
        self.calls.append(("stop", server_id))
        return {"status": "down"}

    def status(self, server_id: str) -> str:
        self.calls.append(("status", server_id))
        return self.status_result

    def access_log_path(self, server_id: str) -> Path:
        return self._log_path

    def shutdown(self) -> None:  # lifespan hook compatibility
        pass


def _free_port() -> int:
    """A port that nothing listens on (bound once then released)."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class TestServerLifecycleRoutes(unittest.TestCase):
    """B5: POST start/stop, GET status, GET log tail."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        store = ConfigStore(Path(self.tmp.name) / "cfg.json")
        app = create_app(config_store=store)
        self.log_path = Path(self.tmp.name) / "srv.access.jsonl"
        self.manager = _FakeServerManager(self.log_path)
        app.state.server_manager = self.manager
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _add_server(self, server: dict) -> None:
        r = self.client.post("/config/servers", json=server)
        self.assertEqual(r.status_code, 201)

    def _add_mock_server(self, server_id: str = "srv") -> None:
        self._add_server({"id": server_id, "system": "github", "mode": "mock_local", "port": 9101})

    def _serve_http(self, status_code: int) -> int:
        """Local HTTP server on an ephemeral port answering every GET."""

        class _Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                self.send_response(status_code)
                self.end_headers()

            def log_message(self, *args: object) -> None:
                pass

        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        return httpd.server_address[1]

    # --- start ---
    def test_start_unknown_server_is_404(self) -> None:
        r = self.client.post("/config/servers/nope/start")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(self.manager.calls, [])

    def test_start_non_mock_local_is_400(self) -> None:
        self._add_server(
            {
                "id": "ext",
                "system": "github",
                "mode": "declared_url",
                "base_url": "http://127.0.0.1:1",
            }
        )
        r = self.client.post("/config/servers/ext/start")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.manager.calls, [])

    def test_start_ok_returns_manager_dict(self) -> None:
        self._add_mock_server()
        r = self.client.post("/config/servers/srv/start")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"status": "up"})
        self.assertEqual(self.manager.calls, [("start", "srv")])

    def test_start_honeypot_is_startable(self) -> None:
        # A honeypot sink reuses the mock_server process; the router must let it
        # start (it is excluded from the allowlist, not from the lifecycle).
        self._add_server({"id": "sink", "system": "shadow_db", "mode": "honeypot", "port": 9113})
        r = self.client.post("/config/servers/sink/start")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.manager.calls, [("start", "sink")])

    def test_start_busy_port_is_200_with_down_and_error(self) -> None:
        # A busy port is a domain result the console renders, not a transport
        # error: HTTP 200 with the manager dict as-is.
        self._add_mock_server()
        self.manager.start_result = {
            "status": "down",
            "error": "port 9101 already in use",
        }
        r = self.client.post("/config/servers/srv/start")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"status": "down", "error": "port 9101 already in use"})

    # --- stop ---
    def test_stop_ok(self) -> None:
        self._add_mock_server()
        r = self.client.post("/config/servers/srv/stop")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"status": "down"})
        self.assertEqual(self.manager.calls, [("stop", "srv")])

    def test_stop_unknown_server_is_404(self) -> None:
        r = self.client.post("/config/servers/nope/stop")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(self.manager.calls, [])

    # --- status ---
    def test_status_unknown_server_is_404(self) -> None:
        r = self.client.get("/config/servers/nope/status")
        self.assertEqual(r.status_code, 404)

    def test_status_mock_local_delegates_to_manager(self) -> None:
        self._add_mock_server()
        self.manager.status_result = "up"
        r = self.client.get("/config/servers/srv/status")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"status": "up"})
        self.assertEqual(self.manager.calls, [("status", "srv")])

    def test_status_declared_url_up_when_reachable(self) -> None:
        port = self._serve_http(200)
        self._add_server(
            {
                "id": "ext",
                "system": "github",
                "mode": "declared_url",
                "base_url": f"http://127.0.0.1:{port}",
            }
        )
        r = self.client.get("/config/servers/ext/status")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"status": "up"})

    def test_status_declared_url_up_even_on_http_error(self) -> None:
        # Any HTTP answer means the server is alive, even 5xx.
        port = self._serve_http(503)
        self._add_server(
            {
                "id": "ext",
                "system": "github",
                "mode": "declared_url",
                "base_url": f"http://127.0.0.1:{port}",
            }
        )
        r = self.client.get("/config/servers/ext/status")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"status": "up"})

    def test_status_declared_url_down_when_unreachable(self) -> None:
        self._add_server(
            {
                "id": "ext",
                "system": "github",
                "mode": "declared_url",
                "base_url": f"http://127.0.0.1:{_free_port()}",
            }
        )
        r = self.client.get("/config/servers/ext/status")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"status": "down"})

    def test_status_real_saas_is_not_applicable(self) -> None:
        self._add_server({"id": "saas", "system": "github", "mode": "real_saas", "owner": "acme"})
        r = self.client.get("/config/servers/saas/status")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"status": "n/a"})

    # --- log tail ---
    def test_log_unknown_server_is_404(self) -> None:
        r = self.client.get("/config/servers/nope/log")
        self.assertEqual(r.status_code, 404)

    def test_log_absent_file_is_empty(self) -> None:
        self._add_mock_server()
        r = self.client.get("/config/servers/srv/log?after=3")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"lines": [], "next": 3})

    def test_log_full_read(self) -> None:
        self._add_mock_server()
        entries = [{"seq": 1, "path": "/health"}, {"seq": 2, "path": "/repos"}]
        self.log_path.write_text("".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")
        r = self.client.get("/config/servers/srv/log")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"lines": entries, "next": 2})

    def test_log_incremental_read_after_n(self) -> None:
        self._add_mock_server()
        entries = [{"seq": i} for i in range(1, 5)]
        self.log_path.write_text("".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")
        r = self.client.get("/config/servers/srv/log?after=2")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"lines": [{"seq": 3}, {"seq": 4}], "next": 4})
