"""POST /runs kind=lane_b_process spawns the agent as a separate OS process.

This is the eBPF-observable launch path (chantier 2 Part C): the agent runs as
its own process (`recette.agent_proc`) so the kernel tracepoints can attribute
it. Container-free: seed a mock agent, launch the process run, assert it reaches
``completed``. Mock-only is enforced (a real-AI agent is refused).
"""

from __future__ import annotations

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

_SCENARIO = [
    {"kind": "tool_call", "tool_name": "read_repo", "tool_args": {"resource": "acme/x"}},
    {"kind": "tool_call", "tool_name": "open_pr", "tool_args": {"resource": "acme/x"}},
    {"kind": "final", "text": "done"},
]


def _wait_terminal(client, run_id, tries=600):  # type: ignore[no-untyped-def]
    for _ in range(tries):
        s = client.get(f"/runs/{run_id}").json()["status"]
        if s in {"completed", "failed", "stopped"}:
            return s
        time.sleep(0.02)
    raise AssertionError("run did not terminate")


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class ProcessRunEndpointTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        store = ConfigStore(Path(self._tmp.name) / "cfg.json")
        store.add_agent(
            {
                "id": "proc-bot",
                "runtime": "lab",
                "ai_mode": "mock",
                "principal": "proc@acme",
                "target_system": "github",
                "goal": "process-mode run",
                "capability_scope": ["read_repo", "open_pr"],
                "scenario": _SCENARIO,
            }
        )
        self._store = store
        self.client = TestClient(create_app(config_store=store, event_store=InMemoryEventStore()))

    def test_process_run_completes(self) -> None:
        r = self.client.post(
            "/runs", json={"kind": "lane_b_process", "params": {"agent_id": "proc-bot"}}
        )
        self.assertEqual(r.status_code, 201, r.text)
        run_id = r.json()["run_id"]
        self.assertEqual(_wait_terminal(self.client, run_id), "completed")
        listed = {x["id"]: x for x in self.client.get("/runs").json()["runs"]}
        self.assertEqual(listed[run_id]["kind"], "lane_b_process")

    def test_unknown_agent_is_rejected(self) -> None:
        r = self.client.post(
            "/runs", json={"kind": "lane_b_process", "params": {"agent_id": "nope"}}
        )
        self.assertEqual(r.status_code, 400)

    def test_real_agent_is_refused(self) -> None:
        self._store.add_agent(
            {
                "id": "real-bot",
                "runtime": "lab",
                "ai_mode": "real",
                "principal": "r@acme",
                "target_system": "github",
                "goal": "x",
                "capability_scope": ["read_repo"],
                "ai_backend_id": "b1",
            }
        )
        r = self.client.post(
            "/runs", json={"kind": "lane_b_process", "params": {"agent_id": "real-bot"}}
        )
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
