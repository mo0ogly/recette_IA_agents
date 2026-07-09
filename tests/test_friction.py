"""Scenario friction: deterministic transient errors force observable retries."""

from __future__ import annotations

import unittest

from recette.events import AgentAction
from recette.forge import LabForge
from recette.friction import friction_tool_output
from recette.lane_b import default_tool_output, run_agent
from recette.llm import LlmDecision, StubLlm


def _action(action_type: str = "open_pr", resource: str = "acme/x") -> AgentAction:
    return AgentAction(
        event_id="E000001",
        seq=1,
        timestamp="T000001",
        agent_id="a1",
        principal="bot@acme",
        target_system="github",
        action_type=action_type,
        mode="write",
        resource=resource,
    )


CFG = {"transient_errors": [{"action_type": "open_pr", "failures": 2, "message": "503 down"}]}


class TestFrictionToolOutput(unittest.TestCase):
    def test_fails_n_times_then_succeeds(self) -> None:
        out = friction_tool_output(CFG)
        first = out(_action())
        second = out(_action())
        third = out(_action())
        self.assertTrue(first.startswith("error: 503 down"))
        self.assertIn("attempt 1/2", first)
        self.assertIn("attempt 2/2", second)
        self.assertEqual(third, default_tool_output(_action()))

    def test_non_matching_action_passes_through(self) -> None:
        out = friction_tool_output(CFG)
        self.assertEqual(out(_action("read_repo")), default_tool_output(_action("read_repo")))

    def test_resource_scoped_rule_only_matches_that_resource(self) -> None:
        cfg = {"transient_errors": [{"action_type": "open_pr", "resource": "acme/x"}]}
        out = friction_tool_output(cfg)
        self.assertEqual(
            out(_action(resource="acme/other")),
            default_tool_output(_action(resource="acme/other")),
        )
        self.assertTrue(out(_action(resource="acme/x")).startswith("error:"))

    def test_malformed_config_is_a_transparent_pass_through(self) -> None:
        for bad in (None, 42, "x", {}, {"transient_errors": "nope"}, {"transient_errors": [7]}):
            self.assertIs(friction_tool_output(bad), default_tool_output)

    def test_deterministic_across_instances(self) -> None:
        a = friction_tool_output(CFG)
        b = friction_tool_output(CFG)
        sequence = [_action(), _action(), _action()]
        self.assertEqual([a(x) for x in sequence], [b(x) for x in sequence])


class TestFrictionInLaneB(unittest.TestCase):
    def _llm(self, repeats: int) -> StubLlm:
        call = LlmDecision(kind="tool_call", tool_name="open_pr", tool_args={"resource": "acme/x"})
        return StubLlm([call] * repeats + [LlmDecision(kind="final", text="done")])

    def test_retry_after_transient_error_is_not_a_no_progress_loop(self) -> None:
        # failures=1: attempt 1 errors, attempt 2 succeeds -- stop_on_repeat
        # must allow the retry (2 executed actions), and the error text is
        # persisted in the step results (legibility).
        result = run_agent(
            agent_id="a1",
            principal="bot@acme",
            target_system="github",
            goal="open a PR",
            capability_scope=["open_pr"],
            llm=self._llm(repeats=3),
            forge=LabForge(),
            stop_on_repeat=True,
            tool_output=friction_tool_output(
                {"transient_errors": [{"action_type": "open_pr", "failures": 1}]}
            ),
        )
        self.assertEqual(len(result.actions), 2)
        self.assertTrue(result.tool_results[0].startswith("error:"))
        self.assertTrue(result.tool_results[1].startswith("ok:"))

    def test_repeat_after_success_still_halts(self) -> None:
        # No friction: the second identical call is a genuine no-progress loop.
        result = run_agent(
            agent_id="a1",
            principal="bot@acme",
            target_system="github",
            goal="open a PR",
            capability_scope=["open_pr"],
            llm=self._llm(repeats=3),
            forge=LabForge(),
            stop_on_repeat=True,
        )
        self.assertEqual(len(result.actions), 1)


if __name__ == "__main__":
    unittest.main()
