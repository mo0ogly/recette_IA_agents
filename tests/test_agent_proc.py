"""Process-mode agent launch: same judged action log as the in-process run (I4).

The eBPF-observable process-mode entrypoint (recette.agent_proc) must run the
EXACT same deterministic Lane B loop as the in-process runner, so discovery
judges an agent identically however it was launched. This asserts the SUBPROCESS
output is byte-identical to the in-process dry_run_lane_b result, and that the
core function is deterministic on replay.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from recette.agent_proc import run_agent_process, set_process_comm

_AGENT = {
    "id": "proc-bot",
    "runtime": "lab",
    "ai_mode": "mock",
    "principal": "proc@acme",
    "target_system": "github",
    "goal": "process-mode: read a repo then open a PR",
    "capability_scope": ["read_repo", "open_pr"],
    "scenario": [
        {"kind": "tool_call", "tool_name": "read_repo", "tool_args": {"resource": "acme/x"}},
        {"kind": "tool_call", "tool_name": "open_pr", "tool_args": {"resource": "acme/x"}},
        {"kind": "final", "text": "done"},
    ],
}


class AgentProcTest(unittest.TestCase):
    def test_run_agent_process_is_deterministic(self) -> None:
        first = json.dumps(run_agent_process(_AGENT), sort_keys=True)
        second = json.dumps(run_agent_process(_AGENT), sort_keys=True)
        self.assertEqual(first, second)
        # It really ran the scenario (two governed tool calls + the actions log).
        self.assertEqual(len(run_agent_process(_AGENT)["actions"]), 2)

    def test_subprocess_matches_in_process(self) -> None:
        in_process = run_agent_process(_AGENT)
        with tempfile.TemporaryDirectory() as tmp:
            agent_file = Path(tmp) / "agent.json"
            agent_file.write_text(json.dumps(_AGENT), encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, "-m", "recette.agent_proc", "--agent-file", str(agent_file)],
                capture_output=True,
                text=True,
                cwd=Path(__file__).resolve().parent.parent,
                timeout=60,
            )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        # The separate OS process yields the SAME judged action log (I4).
        self.assertEqual(json.loads(proc.stdout), in_process)

    def test_set_process_comm_is_best_effort(self) -> None:
        # Never raises; returns a bool whatever the platform/permission.
        self.assertIsInstance(set_process_comm("proc-bot"), bool)

    def test_real_agent_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            run_agent_process({**_AGENT, "ai_mode": "real"})


class _StubLab(BaseHTTPRequestHandler):
    """Minimal lab server: records that a real TCP request arrived."""

    received: list[str] = []

    def log_message(self, *args: object) -> None:
        return

    def do_POST(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
        length = int(self.headers.get("Content-Length", "0") or "0")
        _ = self.rfile.read(length) if length else b""
        type(self).received.append(self.path)
        body = json.dumps({"success": True, "data": {"ok": True}}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class AgentProcServerBoundTest(unittest.TestCase):
    """A server-bound process agent runs through the real ProxyForge -> REAL TCP
    connects (the prerequisite for the eBPF connect surface)."""

    def setUp(self) -> None:
        _StubLab.received = []
        self._srv = HTTPServer(("127.0.0.1", 0), _StubLab)
        self._port = self._srv.server_address[1]
        self._t = threading.Thread(target=self._srv.serve_forever, daemon=True)
        self._t.start()
        self.addCleanup(self._srv.server_close)
        self.addCleanup(self._srv.shutdown)

    def test_server_bound_run_makes_real_connects(self) -> None:
        agent = {**_AGENT, "id": "proc-bound", "server": "gh-lab"}
        servers = [
            {
                "id": "gh-lab",
                "system": "github",
                "mode": "declared_url",
                "base_url": f"http://127.0.0.1:{self._port}",
            }
        ]
        result = run_agent_process(agent, servers)
        # The agent's two tool calls became real HTTP POSTs to the stub lab
        # (real outbound TCP = what the kernel eBPF connect tracepoint observes).
        self.assertEqual(len(result["actions"]), 2)
        self.assertEqual(len(_StubLab.received), 2)
        self.assertTrue(all(p.endswith("/execute") for p in _StubLab.received))


if __name__ == "__main__":
    unittest.main()
