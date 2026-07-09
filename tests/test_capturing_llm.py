"""CapturingLlm: records intent per decision, transparent + fail-safe."""

from __future__ import annotations

import unittest

from recette.capture.capturing_llm import CapturingLlm
from recette.llm import LlmDecision, StubLlm


class TestCapturingLlm(unittest.TestCase):
    def test_records_one_trace_per_decision_with_intent_and_tokens(self) -> None:
        inner = StubLlm(
            [
                LlmDecision(
                    kind="tool_call",
                    tool_name="read_repo",
                    tool_args={"resource": "acme/x"},
                    raw={"usage": {"prompt_tokens": 5, "completion_tokens": 1}},
                )
            ]
        )
        traces = []
        llm = CapturingLlm(inner, agent_id="a1", model="m", sink=traces.append)
        llm.decide(system="s", history=[], tools=[])
        self.assertEqual(len(traces), 1)
        self.assertEqual(traces[0].tool_name, "read_repo")
        self.assertEqual(traces[0].resource, "acme/x")
        self.assertEqual(traces[0].intent, "read_repo:acme/x")
        self.assertEqual(traces[0].prompt_tokens, 5)

    def test_records_decision_text_as_rationale(self) -> None:
        inner = StubLlm(
            [
                LlmDecision(
                    kind="tool_call",
                    tool_name="read_repo",
                    tool_args={"resource": "acme/x"},
                    text="Reading the repo to confirm the default branch.",
                )
            ]
        )
        traces = []
        llm = CapturingLlm(inner, agent_id="a1", model="m", sink=traces.append)
        llm.decide(system="s", history=[], tools=[])
        self.assertEqual(traces[0].rationale, "Reading the repo to confirm the default branch.")

    def test_returns_inner_decision_unchanged(self) -> None:
        inner = StubLlm([LlmDecision(kind="final", text="done")])
        llm = CapturingLlm(inner, agent_id="a1", model="m", sink=lambda _t: None)
        decision = llm.decide(system="s", history=[], tools=[])
        self.assertEqual(decision.kind, "final")
        self.assertEqual(decision.text, "done")

    def test_sink_failure_does_not_break_decide(self) -> None:
        inner = StubLlm([LlmDecision(kind="final", text="done")])

        def boom(_trace) -> None:
            raise RuntimeError("sink down")

        llm = CapturingLlm(inner, agent_id="a1", model="m", sink=boom)
        # decide still returns the inner decision (fail-safe, observation never blocks)
        self.assertEqual(llm.decide(system="s", history=[], tools=[]).kind, "final")

    def test_event_id_is_sequence_derived(self) -> None:
        inner = StubLlm(
            [LlmDecision(kind="tool_call", tool_name="t", tool_args={"resource": "r"})] * 2
        )
        traces = []
        llm = CapturingLlm(inner, agent_id="a1", model="m", sink=traces.append)
        llm.decide(system="s", history=[], tools=[])
        llm.decide(system="s", history=[], tools=[])
        self.assertEqual([t.event_id for t in traces], ["LC000001", "LC000002"])


if __name__ == "__main__":
    unittest.main()
