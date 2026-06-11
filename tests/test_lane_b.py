"""LB3/LB4 tests: the Lane B agent loop and deterministic replay."""

from __future__ import annotations

import unittest

from recette.forge import LabForge
from recette.lane_b import run_agent
from recette.llm import LlmDecision, StubLlm
from recette.recording import Recording, replay_backend


def _script() -> StubLlm:
    return StubLlm(
        [
            LlmDecision(kind="tool_call", tool_name="read_repo", tool_args={"resource": "acme/x"}),
            LlmDecision(
                kind="tool_call",
                tool_name="open_pr",
                tool_args={"resource": "acme/x", "params": {"title": "bump"}},
            ),
            LlmDecision(kind="final", text="done"),
        ]
    )


def _run(llm, forge=None):
    return run_agent(
        agent_id="a1",
        principal="acme-bot@github",
        target_system="github",
        goal="bump dependencies",
        capability_scope=["read_repo", "open_pr"],
        llm=llm,
        forge=forge,
    )


class TestAgentLoop(unittest.TestCase):
    def test_runs_until_final_and_records_actions(self):
        result = _run(_script())
        self.assertEqual([a.action_type for a in result.actions], ["read_repo", "open_pr"])
        self.assertEqual(result.actions[1].resource, "acme/x")
        self.assertEqual(result.actions[1].params, {"title": "bump"})
        # 3 steps recorded (2 tool calls + 1 final)
        self.assertEqual(len(result.recording.steps), 3)
        self.assertEqual(len(result.recording.actions()), 2)

    def test_max_steps_bounds_a_runaway(self):
        loop_forever = StubLlm(
            [LlmDecision(kind="tool_call", tool_name="read_repo", tool_args={"resource": "x"})] * 50
        )
        result = run_agent(
            agent_id="a",
            principal="p",
            target_system="github",
            goal="g",
            capability_scope=["read_repo"],
            llm=loop_forever,
            max_steps=3,
        )
        self.assertEqual(len(result.actions), 3)


class TestReplay(unittest.TestCase):
    def test_replay_reproduces_identical_actions(self):
        first = _run(_script())
        replay = _run(replay_backend(first.recording), forge=LabForge())
        self.assertEqual(
            [a.to_dict() for a in first.actions],
            [a.to_dict() for a in replay.actions],
        )

    def test_recording_round_trips(self):
        rec = _run(_script()).recording
        again = Recording.from_dict(rec.to_dict())
        self.assertEqual(again.to_dict(), rec.to_dict())
        self.assertEqual([d.tool_name for d in again.decisions()], ["read_repo", "open_pr", None])


if __name__ == "__main__":
    unittest.main()
