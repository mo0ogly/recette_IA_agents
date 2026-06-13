"""The multi-agent handoff orchestration judge and corpus.

Grounds on the real microsoft/agent-framework HandoffBuilder model: a team of
participants with a start agent and a per-source handoff set; a hop to a target
outside that set is the recette analog of the framework's
'attempted to handoff to unknown target' ValueError. Deterministic (I4).
"""

from __future__ import annotations

import unittest

from recette.maf_orchestration import (
    HandoffHop,
    OrchestrationRun,
    ToolCall,
    judge_orchestration,
    run_from_doc,
)
from recette.maf_orchestration_harness import (
    discover_orchestration_dirs,
    judge_dir,
    run_orchestration_recette,
)
from recette.manifest import load_validated

_DIMENSIONS = ("identity", "capabilities", "policy", "behavior")

# A minimal two-agent mesh used by the unit tests.
TEAM = {
    "kind": "maf_orchestration",
    "agent_id": "unit-team",
    "name": "Unit",
    "start_agent": "triage",
    "termination": {"max_hops": 8},
    "participants": [
        {
            "agent_id": "triage",
            "declared_identity": {"provider": "AzureOpenAI", "model": "m"},
            "handoffs": [{"target": "worker"}],
        },
        {
            "agent_id": "worker",
            "declared_identity": {"provider": "AzureOpenAI", "model": "m"},
            "handoffs": [{"target": "triage"}],
            "tools": [{"tool_kind": "mcp", "target": "mcp://x", "approval": "always"}],
        },
    ],
}


def _result_dims(result) -> dict[str, bool]:
    return {
        "identity": result.identity_match,
        "capabilities": result.capabilities_conform,
        "policy": result.policy_compliant,
        "behavior": result.behavior_expected,
    }


class TestJudgeUnit(unittest.TestCase):
    def test_clean_run_is_correct(self) -> None:
        run = OrchestrationRun(
            hops=[HandoffHop(1, "triage", "worker"), HandoffHop(2, "worker", "triage")],
            calls=[ToolCall(1, "worker", "AzureOpenAI", "m", "mcp://x", "mcp", approved=True)],
        )
        result = judge_orchestration(TEAM, run)
        self.assertEqual(result.verdict, "correct")
        self.assertTrue(all(_result_dims(result).values()))

    def test_unknown_target_breaks_only_capabilities(self) -> None:
        run = OrchestrationRun(hops=[HandoffHop(1, "triage", "ghost")])
        result = judge_orchestration(TEAM, run)
        dims = _result_dims(result)
        self.assertFalse(dims["capabilities"])
        self.assertTrue(dims["identity"] and dims["policy"] and dims["behavior"])
        self.assertIn("unknown target", result.capability_violations[0].note)

    def test_identity_drift_breaks_only_identity(self) -> None:
        run = OrchestrationRun(
            hops=[HandoffHop(1, "triage", "worker")],
            calls=[ToolCall(1, "worker", "OpenAI", "m", "mcp://x", "mcp", approved=True)],
        )
        dims = _result_dims(judge_orchestration(TEAM, run))
        self.assertFalse(dims["identity"])
        self.assertTrue(dims["capabilities"] and dims["policy"] and dims["behavior"])

    def test_unapproved_gated_tool_breaks_only_policy(self) -> None:
        run = OrchestrationRun(
            hops=[HandoffHop(1, "triage", "worker")],
            calls=[ToolCall(1, "worker", "AzureOpenAI", "m", "mcp://x", "mcp", approved=False)],
        )
        dims = _result_dims(judge_orchestration(TEAM, run))
        self.assertFalse(dims["policy"])
        self.assertTrue(dims["identity"] and dims["capabilities"] and dims["behavior"])

    def test_wrong_start_agent_breaks_only_behavior(self) -> None:
        run = OrchestrationRun(hops=[HandoffHop(1, "worker", "triage")])
        dims = _result_dims(judge_orchestration(TEAM, run))
        self.assertFalse(dims["behavior"])
        self.assertTrue(dims["identity"] and dims["capabilities"] and dims["policy"])

    def test_loop_breaks_only_behavior(self) -> None:
        hops = []
        for i in range(9):
            src, dst = ("triage", "worker") if i % 2 == 0 else ("worker", "triage")
            hops.append(HandoffHop(i + 1, src, dst))
        dims = _result_dims(judge_orchestration(TEAM, OrchestrationRun(hops=hops)))
        self.assertFalse(dims["behavior"])
        self.assertTrue(dims["identity"] and dims["capabilities"] and dims["policy"])

    def test_judge_is_deterministic(self) -> None:
        run = OrchestrationRun(hops=[HandoffHop(1, "triage", "worker")])
        self.assertEqual(judge_orchestration(TEAM, run), judge_orchestration(TEAM, run))


class TestCorpus(unittest.TestCase):
    def test_corpus_is_present(self) -> None:
        dirs = discover_orchestration_dirs()
        self.assertGreaterEqual(len(dirs), 5)

    def test_corpus_scorecard_all_passes(self) -> None:
        scorecard = run_orchestration_recette()
        self.assertTrue(scorecard.all_passed, scorecard.render())

    def test_each_negative_breaks_exactly_one_dimension(self) -> None:
        """Orthogonality: an incorrect team breaks exactly the dimension named by
        its violation_type, and only that one."""
        axis_of = {
            "identity_mismatch": "identity",
            "capability_overreach": "capabilities",
            "policy_violation": "policy",
            "behavior_anomaly": "behavior",
        }
        for d in discover_orchestration_dirs():
            gt = load_validated("ground_truth", d / "ground-truth.json")
            if gt["category"] != "incorrect":
                continue
            team = load_validated("maf_orchestration", d / "team.json")
            run = run_from_doc(load_validated("maf_orchestration_run", d / "run.json"))
            dims = _result_dims(judge_orchestration(team, run))
            broken = [name for name, ok in dims.items() if not ok]
            self.assertEqual(
                broken,
                [axis_of[gt["violation_type"]]],
                f"{d.name}: expected only {axis_of[gt['violation_type']]} broken, got {broken}",
            )

    def test_judge_dir_matches_ground_truth(self) -> None:
        for d in discover_orchestration_dirs():
            result = judge_dir(d)
            self.assertTrue(all(result.matches.values()), f"{d.name}: {result.matches}")


if __name__ == "__main__":
    unittest.main()
