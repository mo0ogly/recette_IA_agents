"""Step-through run view -- deterministic timeline + verdict for the DevUI viewer."""

from __future__ import annotations

import unittest

from recette.maf_orchestration import HandoffHop, OrchestrationRun, ToolCall
from recette.run_view import build_run_view

TEAM = {
    "kind": "maf_orchestration",
    "agent_id": "view-team",
    "name": "View Team",
    "start_agent": "triage",
    "participants": [
        {
            "agent_id": "triage",
            "declared_identity": {"provider": "P", "model": "m"},
            "handoffs": [{"target": "worker"}],
        },
        {
            "agent_id": "worker",
            "declared_identity": {"provider": "P", "model": "m"},
            "tools": [{"tool_kind": "mcp", "target": "mcp://x", "approval": "always"}],
        },
    ],
}


class TestBuildRunView(unittest.TestCase):
    def test_handoff_timeline_and_verdict(self) -> None:
        run = OrchestrationRun(
            hops=[HandoffHop(1, "triage", "worker")],
            calls=[ToolCall(1, "worker", "P", "m", "mcp://x", "mcp", approved=True)],
        )
        view = build_run_view(TEAM, run)
        self.assertEqual(view["verdict"], "correct")
        self.assertEqual(
            set(view["dimensions"]), {"identity", "capabilities", "policy", "behavior"}
        )
        kinds = [s["kind"] for s in view["steps"]]
        self.assertEqual(kinds, ["handoff", "tool"])
        self.assertEqual(view["steps"][0]["label"], "triage -> worker")
        self.assertTrue(view["mermaid"].startswith("flowchart TD"))
        # indices are contiguous 0..n-1 for the slider.
        self.assertEqual([s["index"] for s in view["steps"]], [0, 1])

    def test_order_style_turns(self) -> None:
        team = {
            "kind": "maf_orchestration",
            "style": "sequential",
            "agent_id": "seq",
            "name": "Seq",
            "participants": [
                {"agent_id": "a", "declared_identity": {"provider": "P", "model": "m"}},
                {"agent_id": "b", "declared_identity": {"provider": "P", "model": "m"}},
            ],
        }
        view = build_run_view(team, OrchestrationRun(order=["a", "b"]))
        self.assertEqual([s["kind"] for s in view["steps"]], ["turn", "turn"])
        self.assertEqual([s["agent"] for s in view["steps"]], ["a", "b"])

    def test_violation_surfaces_in_view(self) -> None:
        run = OrchestrationRun(hops=[HandoffHop(1, "triage", "ghost")])
        view = build_run_view(TEAM, run)
        self.assertEqual(view["verdict"], "incorrect")
        self.assertFalse(view["dimensions"]["capabilities"])
        self.assertTrue(view["violations"])

    def test_is_deterministic(self) -> None:
        run = OrchestrationRun(hops=[HandoffHop(1, "triage", "worker")])
        self.assertEqual(build_run_view(TEAM, run), build_run_view(TEAM, run))


if __name__ == "__main__":
    unittest.main()
