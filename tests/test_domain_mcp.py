"""mcp domain tests: catalog specs + realistic deterministic lab handler."""

from __future__ import annotations

import unittest

from recette.lab.domains import mcp as mcp_lab
from recette.platform.catalog import load_catalog
from recette.platform.catalog.domains.mcp import ACTIONS, TARGET_SYSTEM


class TestMcpCatalog(unittest.TestCase):
    def test_target_system(self) -> None:
        self.assertEqual(TARGET_SYSTEM, "mcp")
        for spec in ACTIONS:
            self.assertEqual(spec.target_system, "mcp")

    def test_load_catalog_contains_mcp_actions(self) -> None:
        catalog = load_catalog()
        self.assertIn("mcp", catalog.target_systems())
        for spec in ACTIONS:
            self.assertIsNotNone(catalog.get("mcp", spec.action_type))


class TestMcpLabHandler(unittest.TestCase):
    def test_handler_covers_every_cataloged_action(self) -> None:
        for spec in ACTIONS:
            with self.subTest(action_type=spec.action_type):
                response = mcp_lab.handle(spec.action_type, "agent-x", {"k": "v"})
                self.assertIsInstance(response, dict)
                assert response is not None
                self.assertEqual(response["action"], spec.action_type)
                self.assertEqual(response["resource"], "agent-x")
                self.assertEqual(len(response["result_id"]), 12)
                self.assertNotEqual(response["status"], "simulated")

    def test_invoke_tool_is_realistic(self) -> None:
        resp = mcp_lab.handle("invoke_tool", "web_search", {"tool": "web_search"})
        assert resp is not None
        self.assertEqual(resp["status"], "invoked")
        self.assertTrue(resp["call_id"].startswith("call_"))
        self.assertEqual(resp["tool"], "web_search")
        self.assertFalse(resp["approved"])

    def test_handoff_is_realistic(self) -> None:
        resp = mcp_lab.handle("handoff", "planner", {"to": "executor"})
        assert resp is not None
        self.assertEqual(resp["status"], "transferred")
        self.assertEqual(resp["to_agent"], "executor")
        self.assertTrue(resp["transfer_id"].startswith("ho_"))

    def test_handler_is_deterministic(self) -> None:
        for spec in ACTIONS:
            with self.subTest(action_type=spec.action_type):
                a = mcp_lab.handle(spec.action_type, "agent-y", {"b": 2, "a": 1})
                b = mcp_lab.handle(spec.action_type, "agent-y", {"b": 2, "a": 1})
                self.assertEqual(a, b)

    def test_unknown_action_returns_none(self) -> None:
        self.assertIsNone(mcp_lab.handle("execute_shell", "x", {}))
        self.assertIsNone(mcp_lab.handle("", "x", {}))


if __name__ == "__main__":
    unittest.main()
