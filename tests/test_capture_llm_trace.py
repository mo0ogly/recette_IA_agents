"""LlmCallTrace: intent key + derived totals + serialization."""

from __future__ import annotations

import unittest

from recette.capture.llm_trace import LlmCallTrace


def _trace(**kw) -> LlmCallTrace:
    base = dict(
        seq=1,
        event_id="LC000001",
        agent_id="a1",
        model="llama-3.3-70b-versatile",
        kind="tool_call",
        tool_name="read_repo",
        resource="acme/x",
        prompt_tokens=120,
        completion_tokens=18,
        latency_ms=842,
        error=None,
    )
    base.update(kw)
    return LlmCallTrace(**base)


class TestLlmCallTrace(unittest.TestCase):
    def test_to_dict_has_intent_and_total_tokens(self) -> None:
        d = _trace().to_dict()
        self.assertEqual(d["intent"], "read_repo:acme/x")
        self.assertEqual(d["total_tokens"], 138)
        self.assertEqual(d["latency_ms"], 842)

    def test_intent_of_a_final_thought_has_empty_tool(self) -> None:
        d = _trace(kind="final", tool_name=None, resource="").to_dict()
        self.assertEqual(d["intent"], ":")

    def test_rationale_defaults_empty_and_serializes(self) -> None:
        self.assertEqual(_trace().to_dict()["rationale"], "")
        d = _trace(rationale="Reading first to confirm the branch.").to_dict()
        self.assertEqual(d["rationale"], "Reading first to confirm the branch.")


if __name__ == "__main__":
    unittest.main()
