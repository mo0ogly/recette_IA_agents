"""End-to-end orchestration: drive -> record -> replay -> freeze, deterministic (I4).

Uses StubLlm so the whole pipeline runs offline with no key. The live path swaps
StubLlm for GroqLlm; the recording/replay contract is identical.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from recette.llm import LlmDecision, StubLlm
from recette.maf_orchestration_harness import judge_dir
from recette.orchestrate import (
    OrchestrationRecording,
    drive,
    freeze_to_corpus,
    record,
    replay,
)

HANDOFF_TEAM = {
    "kind": "maf_orchestration",
    "agent_id": "drive-handoff",
    "name": "Drive Handoff",
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

SEQ_TEAM = {
    "kind": "maf_orchestration",
    "style": "sequential",
    "agent_id": "drive-seq",
    "name": "Drive Seq",
    "participants": [
        {"agent_id": "a", "declared_identity": {"provider": "AzureOpenAI", "model": "m"}},
        {"agent_id": "b", "declared_identity": {"provider": "AzureOpenAI", "model": "m"}},
    ],
}


def _tc(name: str, **args) -> LlmDecision:
    return LlmDecision(kind="tool_call", tool_name=name, tool_args=args)


_FINAL = LlmDecision(kind="final", text="done")


class TestDrive(unittest.TestCase):
    def test_handoff_drive_produces_hops_and_calls(self) -> None:
        backend = StubLlm([_tc("handoff_to_worker"), _tc("use_mcp_0", approved=True), _FINAL])
        run = drive(HANDOFF_TEAM, backend)
        self.assertEqual([(h.source, h.target) for h in run.hops], [("triage", "worker")])
        self.assertEqual(len(run.calls), 1)
        self.assertEqual(run.calls[0].agent_id, "worker")
        self.assertEqual(run.calls[0].target, "mcp://x")
        self.assertTrue(run.calls[0].approved)

    def test_sequential_drive_runs_each_once_in_order(self) -> None:
        run = drive(SEQ_TEAM, StubLlm([_FINAL, _FINAL]))
        self.assertEqual(run.order, ["a", "b"])


class TestRecordReplay(unittest.TestCase):
    def test_replay_reproduces_run_and_verdict(self) -> None:
        backend = StubLlm([_tc("handoff_to_worker"), _tc("use_mcp_0", approved=True), _FINAL])
        rec = record(HANDOFF_TEAM, backend, provider="stub")
        run_a, result_a = replay(rec)
        run_b, result_b = replay(rec)
        self.assertEqual(result_a.verdict, "correct")
        self.assertEqual(result_a, result_b)  # I4: replay is deterministic
        self.assertEqual([h.target for h in run_a.hops], [h.target for h in run_b.hops])

    def test_recording_round_trips_through_disk(self) -> None:
        backend = StubLlm([_tc("handoff_to_worker"), _FINAL])
        rec = record(HANDOFF_TEAM, backend)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rec.json"
            rec.save(path)
            loaded = OrchestrationRecording.load(path)
        _, result = replay(loaded)
        self.assertEqual(result.verdict, "correct")

    def test_replay_guard_rejects_divergence(self) -> None:
        rec = record(HANDOFF_TEAM, StubLlm([_tc("handoff_to_worker"), _FINAL]))
        # Corrupt the stored run so the reproduced one no longer matches.
        rec.run.hops.clear()
        with self.assertRaises(ValueError):
            replay(rec)


class TestFreeze(unittest.TestCase):
    def test_freeze_produces_a_valid_corpus_subject(self) -> None:
        rec = record(
            HANDOFF_TEAM,
            StubLlm([_tc("handoff_to_worker"), _tc("use_mcp_0", approved=True), _FINAL]),
        )
        with tempfile.TemporaryDirectory() as tmp:
            out = freeze_to_corpus(rec, tmp, slug="frozen-handoff", category="correct")
            result = judge_dir(out)
            self.assertTrue(all(result.matches.values()), result.matches)
            self.assertEqual(result.predicted_verdict, "correct")

    def test_group_chat_drive_and_freeze(self) -> None:
        team = {
            "kind": "maf_orchestration",
            "style": "group_chat",
            "agent_id": "drive-gc",
            "name": "GC",
            "termination": {"max_hops": 8},
            "participants": [
                {
                    "agent_id": "responder",
                    "declared_identity": {"provider": "AzureOpenAI", "model": "m"},
                },
                {
                    "agent_id": "analyst",
                    "declared_identity": {"provider": "AzureOpenAI", "model": "m"},
                },
            ],
        }
        run = drive(team, StubLlm([_tc("speak_responder"), _tc("speak_analyst"), _FINAL]))
        self.assertEqual(run.order, ["responder", "analyst"])
        rec = record(team, StubLlm([_tc("speak_responder"), _tc("speak_analyst"), _FINAL]))
        _, result = replay(rec)
        self.assertEqual(result.verdict, "correct")


if __name__ == "__main__":
    unittest.main()
