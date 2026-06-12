# tests/test_api_lane_b_run.py
"""U1: a registered Lane B agent runs via the API and streams step frames (stubbed LLM)."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app
    from recette.api.config_store import ConfigStore

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover
    _HAS_FASTAPI = False


def _wait_terminal(client, run_id, tries=200):
    for _ in range(tries):
        s = client.get(f"/runs/{run_id}").json()["status"]
        if s in {"completed", "failed", "stopped"}:
            return s
        time.sleep(0.01)
    raise AssertionError("no terminate")


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class TestLaneBRun(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = store = ConfigStore(Path(self.tmp.name) / "cfg.json")
        store.add_agent(
            {
                "id": "a1",
                "principal": "acme-bot@github",
                "target_system": "github",
                "goal": "bump deps",
                "capability_scope": ["read_repo", "open_pr"],
                "ai_backend_id": "b1",
                "runtime": "lab",
            }
        )
        self.client = TestClient(create_app(config_store=store))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_lane_b_run_streams_steps(self) -> None:
        stub = [
            {"kind": "tool_call", "tool_name": "read_repo", "tool_args": {"resource": "acme/x"}},
            {"kind": "final", "text": "done"},
        ]
        r = self.client.post(
            "/runs", json={"kind": "lane_b", "params": {"agent_id": "a1", "stub_script": stub}}
        )
        self.assertEqual(r.status_code, 201)
        run_id = r.json()["run_id"]
        self.assertEqual(_wait_terminal(self.client, run_id), "completed")
        events = self.client.get(f"/runs/{run_id}/events").json()
        self.assertTrue(any(e["type"] == "step" for e in events))
        self.assertTrue(any(e["type"] == "result" for e in events))

    def test_lane_b_run_with_dangling_server_fails_safely(self) -> None:
        """B6 (I5 fail-safe): a server reference absent from the registry fails
        the run explicitly -- never a silent fallback to the default forge."""
        self.store.add_agent(
            {
                "id": "a-ghost",
                "principal": "acme-bot@github",
                "target_system": "github",
                "goal": "bump deps",
                "capability_scope": ["read_repo"],
                "ai_backend_id": "b1",
                "runtime": "lab",
                "server": "gh-ghost",
            }
        )
        stub = [
            {"kind": "tool_call", "tool_name": "read_repo", "tool_args": {"resource": "acme/x"}},
            {"kind": "final", "text": "done"},
        ]
        r = self.client.post(
            "/runs", json={"kind": "lane_b", "params": {"agent_id": "a-ghost", "stub_script": stub}}
        )
        self.assertEqual(r.status_code, 201)
        run_id = r.json()["run_id"]
        self.assertEqual(_wait_terminal(self.client, run_id), "failed")
        run = self.client.get(f"/runs/{run_id}").json()
        self.assertIn("gh-ghost", run["error"])
        events = self.client.get(f"/runs/{run_id}/events").json()
        self.assertTrue(any(e["type"] == "error" for e in events))
        # Fail-safe: the action never executed anywhere (no step frame).
        self.assertFalse(any(e["type"] == "step" for e in events))

    def test_lane_b_run_with_declared_url_server_routes_to_it(self) -> None:
        """B6 (I5): an agent bound to a declared_url server executes its actions
        against that server over the lab wire format."""
        import json
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer

        received: list[dict] = []

        class _StubLab(BaseHTTPRequestHandler):
            def log_message(self, *args: object) -> None:
                return

            def do_POST(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
                length = int(self.headers.get("Content-Length", "0") or "0")
                body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
                received.append({"path": self.path, "body": body})
                payload = json.dumps({"success": True, "data": {"ok": True}}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        server = HTTPServer(("127.0.0.1", 0), _StubLab)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            self.store.add_server(
                {
                    "id": "gh-stub",
                    "system": "github",
                    "mode": "declared_url",
                    "base_url": f"http://127.0.0.1:{port}",
                }
            )
            self.store.add_agent(
                {
                    "id": "a-routed",
                    "principal": "acme-bot@github",
                    "target_system": "github",
                    "goal": "bump deps",
                    "capability_scope": ["read_repo"],
                    "ai_backend_id": "b1",
                    "runtime": "lab",
                    "server": "gh-stub",
                }
            )
            stub = [
                {
                    "kind": "tool_call",
                    "tool_name": "read_repo",
                    "tool_args": {"resource": "acme/x"},
                },
                {"kind": "final", "text": "done"},
            ]
            r = self.client.post(
                "/runs",
                json={"kind": "lane_b", "params": {"agent_id": "a-routed", "stub_script": stub}},
            )
            self.assertEqual(r.status_code, 201)
            run_id = r.json()["run_id"]
            self.assertEqual(_wait_terminal(self.client, run_id), "completed")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["path"], "/github/execute")
        self.assertEqual(received[0]["body"]["action_type"], "read_repo")
        self.assertEqual(received[0]["body"]["resource"], "acme/x")

    def test_lane_b_run_openai_compat_backend_uses_base_url(self) -> None:
        """A4: an openai_compat ai_backend's base_url reaches build_llm -- the agent
        runs keyless against a local OpenAI-wire stub server, end to end."""
        import json
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer

        received: list[str] = []

        class _StubOpenAi(BaseHTTPRequestHandler):
            def log_message(self, *args: object) -> None:
                return

            def do_POST(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
                received.append(self.path)
                payload = json.dumps(
                    {"choices": [{"message": {"content": "done"}}]}
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        server = HTTPServer(("127.0.0.1", 0), _StubOpenAi)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            self.store.add_ai_backend(
                {
                    "id": "b-compat",
                    "provider": "openai_compat",
                    "model": "qwen2.5",
                    "base_url": f"http://127.0.0.1:{port}/v1",
                }
            )
            self.store.add_agent(
                {
                    "id": "a-compat",
                    "principal": "acme-bot@github",
                    "target_system": "github",
                    "goal": "bump deps",
                    "capability_scope": ["read_repo"],
                    "ai_backend_id": "b-compat",
                    "runtime": "lab",
                }
            )
            r = self.client.post(
                "/runs", json={"kind": "lane_b", "params": {"agent_id": "a-compat"}}
            )
            self.assertEqual(r.status_code, 201)
            run_id = r.json()["run_id"]
            self.assertEqual(_wait_terminal(self.client, run_id), "completed")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
        self.assertEqual(received, ["/v1/chat/completions"])

    def test_register_agent_then_in_catalog(self) -> None:
        r = self.client.post(
            "/agents/register",
            json={
                "id": "a2",
                "principal": "p",
                "target_system": "github",
                "goal": "g",
                "capability_scope": ["read_repo"],
                "ai_backend_id": "b1",
                "runtime": "lab",
            },
        )
        self.assertEqual(r.status_code, 201)
        lane_b_ids = {a["id"] for a in self.client.get("/agents").json()["lane_b"]}
        self.assertIn("a2", lane_b_ids)
