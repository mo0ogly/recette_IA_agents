# tests/test_api_run_autostart_server.py
"""A run self-heals its target lab server: an agent bound to a mock_local server
that is NOT running gets it started at launch, instead of failing with
"target server stopped or unreachable at 127.0.0.1:<port>".

Regression guard: previously the mock_local servers were started only at
`platform up` (best-effort); a boot-time failure, or an API started another way,
left the run to fail on connection-refused. The run launch now brings a down
port-bound target up first (idempotent via status)."""

from __future__ import annotations

import socket
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


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_terminal(client, run_id, tries=300):
    for _ in range(tries):
        s = client.get(f"/runs/{run_id}").json()["status"]
        if s in {"completed", "failed", "stopped"}:
            return s
        time.sleep(0.01)
    raise AssertionError("no terminate")


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class TestRunAutostartsTarget(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        store = ConfigStore(Path(self.tmp.name) / "cfg.json")
        self.port = _free_port()
        store.add_server(
            {"id": "gh-mock", "system": "github", "mode": "mock_local", "port": self.port}
        )
        store.add_agent(
            {
                "id": "a1",
                "principal": "acme-bot@github",
                "target_system": "github",
                "goal": "read the repo",
                "capability_scope": ["read_repo"],
                "ai_backend_id": "b1",
                "runtime": "lab",
                "server": "gh-mock",
            }
        )
        self.app = create_app(config_store=store)
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        try:
            self.app.state.server_manager.shutdown()
        except Exception:  # pragma: no cover - best-effort teardown
            pass
        self.tmp.cleanup()

    def test_run_autostarts_the_target_mock_local_server(self) -> None:
        sm = self.app.state.server_manager
        # Precondition: the target is NOT running.
        self.assertEqual(sm.status("gh-mock"), "down")

        stub = [
            {"kind": "tool_call", "tool_name": "read_repo", "tool_args": {"resource": "acme/x"}},
            {"kind": "final", "text": "done"},
        ]
        r = self.client.post(
            "/runs", json={"kind": "lane_b", "params": {"agent_id": "a1", "stub_script": stub}}
        )
        self.assertEqual(r.status_code, 201)
        run_id = r.json()["run_id"]

        # The run completes because its target was brought up at launch (no
        # connection-refused), and the server is up afterwards.
        self.assertEqual(_wait_terminal(self.client, run_id), "completed")
        self.assertEqual(sm.status("gh-mock"), "up")
