# tests/test_api_proxy_traces_lane_b.py
"""E2E: a REAL Lane B agent's side effects are recorded in the debug trace ring.

This is the end-to-end answer to "does it work with our agents?": a registered
agent, bound to a (live) server, runs its tool calls through the I5 proxy; with
AGENTRAIL_PROXY_DEBUG on, every side effect shows up in GET /proxy/traces. With
debug off, the same run records nothing (parametrable, R5).
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app
    from recette.api.config_store import ConfigStore
    from recette.platform.eventstore.memory_store import InMemoryEventStore

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover - depends on the [api] extra
    _HAS_FASTAPI = False


class _StubLab(BaseHTTPRequestHandler):
    """Minimal lab speaking the wire format (POST /{system}/execute -> envelope)."""

    def log_message(self, *args: object) -> None:
        return

    def do_POST(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
        length = int(self.headers.get("Content-Length", "0") or "0")
        _ = self.rfile.read(length) if length else b""
        payload = json.dumps({"success": True, "data": {"ok": True}}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _wait_terminal(client, run_id, tries=200):  # type: ignore[no-untyped-def]
    for _ in range(tries):
        s = client.get(f"/runs/{run_id}").json()["status"]
        if s in {"completed", "failed", "stopped"}:
            return s
        time.sleep(0.01)
    raise AssertionError("run did not terminate")


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class LaneBProxyTracesTest(unittest.TestCase):
    def setUp(self) -> None:
        self._server = HTTPServer(("127.0.0.1", 0), _StubLab)
        self._port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(lambda: os.environ.pop("AGENTRAIL_PROXY_DEBUG", None))

    def tearDown(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    def _client(self, *, debug: bool) -> TestClient:
        if debug:
            os.environ["AGENTRAIL_PROXY_DEBUG"] = "on"
        else:
            os.environ.pop("AGENTRAIL_PROXY_DEBUG", None)
        store = ConfigStore(Path(self._tmp.name) / "cfg.json")
        store.add_server(
            {
                "id": "gh-lab",
                "system": "github",
                "mode": "declared_url",
                "base_url": f"http://127.0.0.1:{self._port}",
            }
        )
        store.add_agent(
            {
                "id": "ci-bot",
                "principal": "acme-bot@github",
                "target_system": "github",
                "goal": "bump deps",
                "capability_scope": ["read_repo", "open_pr"],
                "ai_backend_id": "b1",
                "runtime": "lab",
                "server": "gh-lab",
            }
        )
        return TestClient(create_app(config_store=store, event_store=InMemoryEventStore()))

    _STUB = [
        {"kind": "tool_call", "tool_name": "read_repo", "tool_args": {"resource": "acme/x"}},
        {"kind": "tool_call", "tool_name": "open_pr", "tool_args": {"resource": "acme/x"}},
        {"kind": "final", "text": "done"},
    ]

    def _run_agent(self, client: TestClient) -> None:
        r = client.post(
            "/runs",
            json={"kind": "lane_b", "params": {"agent_id": "ci-bot", "stub_script": self._STUB}},
        )
        self.assertEqual(r.status_code, 201, r.text)
        self.assertEqual(_wait_terminal(client, r.json()["run_id"]), "completed")

    def test_real_agent_side_effects_are_traced_when_debug_on(self) -> None:
        client = self._client(debug=True)
        self._run_agent(client)
        body = client.get("/proxy/traces").json()
        self.assertTrue(body["debug_enabled"])
        traced = [(t["agent_id"], t["action_type"], t["ok"]) for t in body["traces"]]
        # Both tool calls of the real agent went through the proxy and were traced.
        self.assertIn(("ci-bot", "read_repo", True), traced)
        self.assertIn(("ci-bot", "open_pr", True), traced)
        # Each successful side effect carries a side_effect_hash (audit, I1/I5).
        self.assertTrue(all(t["side_effect_hash"] for t in body["traces"]))

    def test_same_agent_run_records_nothing_when_debug_off(self) -> None:
        client = self._client(debug=False)
        self._run_agent(client)
        body = client.get("/proxy/traces").json()
        self.assertFalse(body["debug_enabled"])
        self.assertEqual(body["traces"], [])


if __name__ == "__main__":
    unittest.main()
