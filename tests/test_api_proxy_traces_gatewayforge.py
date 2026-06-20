# tests/test_api_proxy_traces_gatewayforge.py
"""E2E: a SERVER-LESS governed agent's exchanges are recorded too (GatewayForge).

Before this, only proxy-bound agents (ProxyForge + TracingProxy) appeared in
/proxy and /discovery-exchange; a server-less agent ran through GatewayForge and
was invisible to those consoles. This asserts the gap is closed: with
INSPECT_IA_AGENTS_PROXY_DEBUG on, a server-less agent's tool calls show up in
GET /proxy/traces (stamped with the run), and with debug off nothing is
recorded (parametrable, R5). The lab need not be reachable -- the governed
outcome (executed or not) is what is traced, so the test is hermetic.
"""

from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app
    from recette.api.config_store import ConfigStore
    from recette.platform.eventstore.memory_store import InMemoryEventStore

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover - depends on the [api] extra
    _HAS_FASTAPI = False

_STUB = [
    {"kind": "tool_call", "tool_name": "read_repo", "tool_args": {"resource": "acme/x"}},
    {"kind": "tool_call", "tool_name": "open_pr", "tool_args": {"resource": "acme/x"}},
    {"kind": "final", "text": "done"},
]


def _wait_terminal(client, run_id, tries=200):  # type: ignore[no-untyped-def]
    for _ in range(tries):
        s = client.get(f"/runs/{run_id}").json()["status"]
        if s in {"completed", "failed", "stopped"}:
            return s
        time.sleep(0.01)
    raise AssertionError("run did not terminate")


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class GatewayForgeTracesTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(lambda: os.environ.pop("INSPECT_IA_AGENTS_PROXY_DEBUG", None))

    def _client(self, *, debug: bool) -> TestClient:
        if debug:
            os.environ["INSPECT_IA_AGENTS_PROXY_DEBUG"] = "on"
        else:
            os.environ.pop("INSPECT_IA_AGENTS_PROXY_DEBUG", None)
        store = ConfigStore(Path(self._tmp.name) / "cfg.json")
        # No `server` binding -> the governed lab path (GatewayForge).
        store.add_agent(
            {
                "id": "gov-bot",
                "principal": "acme-bot@github",
                "target_system": "github",
                "goal": "bump deps",
                "capability_scope": ["read_repo", "open_pr"],
                "ai_backend_id": "b1",
                "runtime": "lab",
            }
        )
        return TestClient(create_app(config_store=store, event_store=InMemoryEventStore()))

    def _run(self, client: TestClient) -> str:
        r = client.post(
            "/runs",
            json={"kind": "lane_b", "params": {"agent_id": "gov-bot", "stub_script": _STUB}},
        )
        self.assertEqual(r.status_code, 201, r.text)
        run_id = r.json()["run_id"]
        _wait_terminal(client, run_id)
        return run_id

    def test_server_less_agent_exchanges_are_traced_when_debug_on(self) -> None:
        client = self._client(debug=True)
        run_id = self._run(client)
        body = client.get("/proxy/traces").json()
        self.assertTrue(body["debug_enabled"])
        actions = {t["action_type"] for t in body["traces"]}
        # The server-less agent's tool calls now reach the proxy/discovery console.
        self.assertIn("read_repo", actions)
        self.assertIn("open_pr", actions)
        self.assertTrue(all(t["run_id"] == run_id for t in body["traces"]))

    def test_server_less_agent_records_nothing_when_debug_off(self) -> None:
        client = self._client(debug=False)
        self._run(client)
        body = client.get("/proxy/traces").json()
        self.assertFalse(body["debug_enabled"])
        self.assertEqual(body["traces"], [])

    def test_traces_feed_the_discovery_exchange_overlay(self) -> None:
        # The overlay endpoint now sees the server-less agent as a detected agent
        # with identified hook exchanges (the point of task a).
        client = self._client(debug=True)
        run_id = self._run(client)
        overlay = client.get("/proxy/discovery-exchange", params={"run_id": run_id}).json()
        self.assertIn("gov-bot", [a["agent_id"] for a in overlay["agents"]])
        hook = [e for e in overlay["exchanges"] if e["kind"] == "hook"]
        self.assertTrue(hook)
        self.assertTrue(all(e["identified"] for e in hook))


if __name__ == "__main__":
    unittest.main()
