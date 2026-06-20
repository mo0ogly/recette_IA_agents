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
import unittest
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


if __name__ == "__main__":
    unittest.main()
