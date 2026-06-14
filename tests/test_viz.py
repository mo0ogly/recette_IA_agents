"""Mermaid auto-viz of a team / run -- deterministic, per style.

Output conventions mirror agent-framework _viz.py (flowchart TD, id["label"]
nodes, a --> b edges, a -. label .-> b for manager edges, ((fan-in)) join).
"""

from __future__ import annotations

import unittest

from recette.maf_orchestration import HandoffHop, OrchestrationRun, ToolCall
from recette.viz import _nid, run_mermaid, team_mermaid


def _ident(provider: str = "P", model: str = "m") -> dict:
    return {"provider": provider, "model": model}


HANDOFF = {
    "kind": "maf_orchestration",
    "agent_id": "t",
    "name": "T",
    "start_agent": "triage",
    "participants": [
        {"agent_id": "triage", "declared_identity": _ident(), "handoffs": [{"target": "worker"}]},
        {"agent_id": "worker", "declared_identity": _ident(), "handoffs": [{"target": "triage"}]},
    ],
}


def _team(style: str) -> dict:
    return {
        "kind": "maf_orchestration",
        "style": style,
        "agent_id": "t",
        "name": "T",
        "participants": [
            {"agent_id": "a", "declared_identity": _ident()},
            {"agent_id": "b", "declared_identity": _ident()},
        ],
    }


class TestTeamMermaid(unittest.TestCase):
    def test_header_and_deterministic(self) -> None:
        out = team_mermaid(HANDOFF)
        self.assertTrue(out.startswith("flowchart TD"))
        self.assertEqual(out, team_mermaid(HANDOFF))

    def test_handoff_marks_start_and_edges(self) -> None:
        out = team_mermaid(HANDOFF)
        self.assertIn('triage["triage (Start)"];', out)
        self.assertIn("triage --> worker;", out)
        self.assertIn("worker --> triage;", out)

    def test_sequential_is_a_chain(self) -> None:
        self.assertIn("a --> b;", team_mermaid(_team("sequential")))

    def test_concurrent_has_fan_in(self) -> None:
        out = team_mermaid(_team("concurrent"))
        self.assertIn("agg((fan-in));", out)
        self.assertIn("dispatch --> a;", out)
        self.assertIn("a --> agg;", out)

    def test_manager_styles_use_dotted_edges(self) -> None:
        self.assertIn("manager -. speak .-> a;", team_mermaid(_team("group_chat")))
        self.assertIn("manager -. next_speaker .-> a;", team_mermaid(_team("magentic")))


class TestRunMermaid(unittest.TestCase):
    def test_hops_become_numbered_edges(self) -> None:
        run = OrchestrationRun(
            hops=[HandoffHop(1, "triage", "worker"), HandoffHop(2, "worker", "triage")],
            calls=[ToolCall(1, "worker", "P", "m", "mcp://x", "mcp", approved=True)],
        )
        out = run_mermaid(HANDOFF, run)
        self.assertTrue(out.startswith("flowchart TD"))
        self.assertIn("triage -->|1| worker;", out)
        self.assertIn("worker -->|2| triage;", out)
        self.assertIn("mcp", out)  # tool call rendered

    def test_order_becomes_numbered_chain(self) -> None:
        out = run_mermaid(_team("sequential"), OrchestrationRun(order=["a", "b"]))
        self.assertIn("a -->|1| b;", out)


class TestSanitize(unittest.TestCase):
    def test_non_alpha_prefixed(self) -> None:
        self.assertEqual(_nid("https://x.y/z"), "https___x_y_z")  # starts with a letter
        self.assertEqual(_nid("3p"), "n_3p")  # starts with a digit -> n_ prefix
        self.assertEqual(_nid("agent"), "agent")


if __name__ == "__main__":
    unittest.main()
