"""Checkpoint / time-travel: replay a run prefix, then reproduce or branch (I4)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from recette.checkpoint import Checkpoint, checkpoint, partial_run, resume
from recette.llm import LlmDecision, ReplayLlm, StubLlm
from recette.orchestrate import record

TEAM = {
    "kind": "maf_orchestration",
    "agent_id": "cp-team",
    "name": "CP",
    "start_agent": "triage",
    "termination": {"max_hops": 8},
    "participants": [
        {
            "agent_id": "triage",
            "declared_identity": {"provider": "P", "model": "m"},
            "handoffs": [{"target": "refund"}, {"target": "order"}],
        },
        {
            "agent_id": "refund",
            "declared_identity": {"provider": "P", "model": "m"},
            "handoffs": [{"target": "triage"}],
        },
        {
            "agent_id": "order",
            "declared_identity": {"provider": "P", "model": "m"},
            "handoffs": [{"target": "triage"}],
        },
    ],
}


def _tc(name: str) -> LlmDecision:
    return LlmDecision(kind="tool_call", tool_name=name)


_FINAL = LlmDecision(kind="final")
# Full run: triage -> refund, refund -> triage, triage -> order, stop.
_DECISIONS = [_tc("handoff_to_refund"), _tc("handoff_to_triage"), _tc("handoff_to_order"), _FINAL]


def _full_recording():  # type: ignore[no-untyped-def]
    return record(TEAM, StubLlm(list(_DECISIONS)))


class TestCheckpoint(unittest.TestCase):
    def test_partial_run_stops_at_checkpoint(self) -> None:
        cp = checkpoint(_full_recording(), after=1)  # only triage -> refund
        run = partial_run(cp)
        self.assertEqual([(h.source, h.target) for h in run.hops], [("triage", "refund")])

    def test_resume_with_original_tail_reproduces_full_run(self) -> None:
        rec = _full_recording()
        cp = checkpoint(rec, after=1)
        # Tail = the rest of the original decisions -> time-travel reproduces the run.
        run = resume(cp, ReplayLlm(list(_DECISIONS[1:])))
        self.assertEqual(
            [(h.source, h.target) for h in run.hops],
            [("triage", "refund"), ("refund", "triage"), ("triage", "order")],
        )

    def test_resume_with_different_tail_branches(self) -> None:
        cp = checkpoint(_full_recording(), after=1)  # replayed: triage -> refund
        # Branch: from refund, go back to triage then stop (a different tail).
        run = resume(cp, StubLlm([_tc("handoff_to_triage"), _FINAL]))
        self.assertEqual(
            [(h.source, h.target) for h in run.hops],
            [("triage", "refund"), ("refund", "triage")],
        )

    def test_checkpoint_round_trips_through_disk(self) -> None:
        cp = checkpoint(_full_recording(), after=2, label="mid")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cp.json"
            cp.save(path)
            loaded = Checkpoint.load(path)
        self.assertEqual(loaded.label, "mid")
        self.assertEqual(len(loaded.prefix), 2)
        run = partial_run(loaded)
        self.assertEqual(len(run.hops), 2)

    def test_negative_after_rejected(self) -> None:
        with self.assertRaises(ValueError):
            checkpoint(_full_recording(), after=-1)


if __name__ == "__main__":
    unittest.main()
