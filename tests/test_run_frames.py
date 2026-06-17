"""WS-B: granular tool-call frame derivation is pure and deterministic (I4)."""

from __future__ import annotations

import unittest

from recette.api.run_frames import tool_call_frame
from recette.llm import LlmDecision
from recette.recording import RecordedStep


class TestToolCallFrame(unittest.TestCase):
    def test_tool_call_step_yields_frame_with_args_and_correlation(self) -> None:
        step = RecordedStep(
            decision=LlmDecision(
                kind="tool_call",
                tool_name="read_repo",
                tool_args={"resource": "acme/x"},
            ),
            action={"event_id": "evt-0001", "action_type": "read_repo"},
        )
        frame = tool_call_frame(3, step)
        assert frame is not None
        self.assertEqual(frame["index"], 3)
        self.assertEqual(frame["name"], "read_repo")
        self.assertEqual(frame["args"], {"resource": "acme/x"})
        # Correlation to the proxy-trace network log is by the action event_id.
        self.assertEqual(frame["event_id"], "evt-0001")

    def test_final_step_yields_no_frame(self) -> None:
        step = RecordedStep(decision=LlmDecision(kind="final", text="done"))
        self.assertIsNone(tool_call_frame(0, step))

    def test_accepts_plain_dict_step(self) -> None:
        step = {
            "decision": {"kind": "tool_call", "tool_name": "open_pr", "tool_args": {}},
            "action": {"event_id": "evt-0002"},
        }
        frame = tool_call_frame(1, step)
        assert frame is not None
        self.assertEqual(frame["name"], "open_pr")
        self.assertEqual(frame["event_id"], "evt-0002")

    def test_is_pure_same_input_same_output(self) -> None:
        step = RecordedStep(
            decision=LlmDecision(kind="tool_call", tool_name="t", tool_args={"a": 1}),
            action={"event_id": "e"},
        )
        self.assertEqual(tool_call_frame(2, step), tool_call_frame(2, step))


if __name__ == "__main__":
    unittest.main()
