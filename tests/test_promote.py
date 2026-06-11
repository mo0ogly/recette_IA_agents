"""LB5/LB7 tests: promote a recording to a Lane A golden + agent CLI (replay/freeze)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from recette.__main__ import main
from recette.harness import run_recette
from recette.lane_b import run_agent
from recette.llm import LlmDecision, StubLlm
from recette.promote import freeze_recording
from recette.recording import Recording


def _recording() -> Recording:
    # Read + bounded-write only -> a clean "correct" agent (no unapproved escalate).
    llm = StubLlm(
        [
            LlmDecision(kind="tool_call", tool_name="read_repo", tool_args={"resource": "acme/x"}),
            LlmDecision(kind="tool_call", tool_name="open_pr", tool_args={"resource": "acme/x"}),
            LlmDecision(kind="final", text="done"),
        ]
    )
    return run_agent(
        agent_id="lb-promoted-bot",
        principal="acme-promoted@github",
        target_system="github",
        goal="open a dependency PR",
        capability_scope=["read_repo", "open_pr"],
        llm=llm,
    ).recording


class TestPromotion(unittest.TestCase):
    def test_freeze_writes_valid_artifacts_that_pass_the_recette(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent_dir = freeze_recording(_recording(), Path(tmp) / "correct")
            for f in ("manifest.json", "scenario.json", "ground-truth.json"):
                self.assertTrue((agent_dir / f).exists(), f)
            # Round-trip: the promoted golden must pass the identification recette (R14).
            scorecard = run_recette(Path(tmp))
            self.assertTrue(scorecard.all_passed, "\n" + scorecard.render())

    def test_empty_recording_is_not_promotable(self):
        empty = Recording(agent_id="x", principal="p", target_system="github", goal="g")
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(ValueError):
            freeze_recording(empty, tmp)


class TestAgentCli(unittest.TestCase):
    def test_replay_then_freeze_via_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            rec_path = Path(tmp) / "run.recording.json"
            _recording().save(rec_path)

            self.assertEqual(main(["agent", "replay", str(rec_path)]), 0)
            self.assertEqual(
                main(["agent", "freeze", str(rec_path), "--out", str(Path(tmp) / "correct")]), 0
            )
            self.assertTrue((Path(tmp) / "correct" / "lb-promoted-bot" / "manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
