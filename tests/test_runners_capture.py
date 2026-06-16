"""T6: opt-in CapturingLlm wrap in the lane_b runner is transparent.

With a capture sink the runner collects an LlmCallTrace per decision; the run's
actions still execute unchanged (capture never alters the decide->act loop).
"""

from __future__ import annotations

import unittest

from recette.api.runners import build_stub_llm, make_lane_b_runner
from recette.capture.llm_trace import LlmCallTrace

_SCRIPT = [
    {"kind": "tool_call", "tool_name": "read_repo", "tool_args": {"resource": "acme/x"}},
    {"kind": "final", "text": "done"},
]

_AGENT = {
    "id": "cap-a1",
    "runtime": "lab",
    "ai_mode": "mock",
    "principal": "bot@acme",
    "target_system": "github",
    "goal": "Inventory repositories",
    "capability_scope": ["read_repo"],
    "scenario": _SCRIPT,
}


def _frames_of(frames: list[tuple[str, dict]], kind: str) -> list[dict]:
    return [data for k, data in frames if k == kind]


class TestRunnerCapture(unittest.TestCase):
    def test_capture_sink_collects_traces_without_changing_the_run(self) -> None:
        traces: list[LlmCallTrace] = []
        frames: list[tuple[str, dict]] = []
        runner = make_lane_b_runner(_AGENT, build_stub_llm(_SCRIPT), capture_sink=traces.append)
        runner({}, lambda kind, data: frames.append((kind, data)), lambda: False)

        # the run still produced its action (transparent)
        results = _frames_of(frames, "result")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["actions"][0]["action_type"], "read_repo")

        # and capture observed the tool-call decision in-process
        self.assertTrue(traces)
        self.assertEqual(traces[0].agent_id, "cap-a1")
        self.assertEqual(traces[0].intent, "read_repo:acme/x")

    def test_default_runner_has_no_capture_overhead(self) -> None:
        # No sink -> no wrap, zero behaviour change (the run still works).
        frames: list[tuple[str, dict]] = []
        runner = make_lane_b_runner(_AGENT, build_stub_llm(_SCRIPT))
        runner({}, lambda kind, data: frames.append((kind, data)), lambda: False)
        self.assertEqual(len(_frames_of(frames, "result")), 1)


if __name__ == "__main__":
    unittest.main()
