"""LB2 tests: tool registry bridging LLM tool calls to the forge."""

from __future__ import annotations

import unittest

from recette.forge import LabForge
from recette.llm import LlmDecision
from recette.tools import build_tools, execute_tool, tool_spec


class TestToolRegistry(unittest.TestCase):
    def test_tool_spec_has_resource_param(self):
        spec = tool_spec("open_pr")
        self.assertEqual(spec.name, "open_pr")
        self.assertIn("resource", spec.parameters["required"])

    def test_tool_spec_unknown_action_raises(self):
        with self.assertRaises(ValueError):
            tool_spec("delete_everything")

    def test_build_tools_is_sorted_and_deduped(self):
        tools = build_tools(["open_pr", "read_repo", "open_pr"])
        self.assertEqual([t.name for t in tools], ["open_pr", "read_repo"])


class TestExecuteTool(unittest.TestCase):
    def setUp(self):
        self.forge = LabForge()

    def _decide(self, name, args):
        return LlmDecision(kind="tool_call", tool_name=name, tool_args=args)

    def test_executes_through_forge_and_records_action(self):
        action = execute_tool(
            self.forge,
            agent_id="a1",
            principal="acme-bot@github",
            target_system="github",
            decision=self._decide("open_pr", {"resource": "acme/x", "params": {"title": "t"}}),
        )
        self.assertEqual(action.action_type, "open_pr")
        self.assertEqual(action.target_system, "github")
        self.assertEqual(action.resource, "acme/x")
        self.assertEqual(action.mode, "write")
        self.assertEqual(action.params, {"title": "t"})
        self.assertEqual(len(self.forge.action_log), 1)

    def test_leftover_args_become_params(self):
        action = execute_tool(
            self.forge,
            agent_id="a1",
            principal="p",
            target_system="gitlab",
            decision=self._decide("read_repo", {"resource": "acme/y", "ref": "main"}),
        )
        self.assertEqual(action.params, {"ref": "main"})
        self.assertEqual(action.mode, "read")

    def test_non_tool_call_raises(self):
        with self.assertRaises(ValueError):
            execute_tool(
                self.forge,
                agent_id="a",
                principal="p",
                target_system="github",
                decision=LlmDecision(kind="final", text="done"),
            )

    def test_unknown_tool_raises(self):
        with self.assertRaises(ValueError):
            execute_tool(
                self.forge,
                agent_id="a",
                principal="p",
                target_system="github",
                decision=self._decide("rm_rf", {"resource": "x"}),
            )


if __name__ == "__main__":
    unittest.main()
