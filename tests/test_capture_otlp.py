"""Gap #4: capture-sourced OTLP spans carry gen_ai.usage tokens (+ cost). I4 pure."""

from __future__ import annotations

import unittest

from recette.otel import COST_USD, USAGE_INPUT, USAGE_OUTPUT, capture_spans, to_otlp


def _d(agent: str, tool: str | None, lat: int, pt: int, ct: int, cost: float | None = None) -> dict:
    out = {
        "agent_id": agent,
        "tool_name": tool,
        "resource": "acme/x",
        "prompt_tokens": pt,
        "completion_tokens": ct,
        "latency_ms": lat,
    }
    if cost is not None:
        out["cost"] = cost
    return out


class TestCaptureSpans(unittest.TestCase):
    def test_root_plus_tool_spans_with_usage_attributes(self) -> None:
        traces = [_d("bot", "read_repo", 120, 40, 12, cost=0.0011), _d("bot", None, 50, 5, 5)]
        spans = capture_spans(traces, "bot")
        # root invoke_agent + one execute_tool (the final answer carries no span).
        self.assertEqual(len(spans), 2)
        tool = spans[1]
        self.assertEqual(tool.attributes[USAGE_INPUT], 40)
        self.assertEqual(tool.attributes[USAGE_OUTPUT], 12)
        self.assertEqual(tool.attributes[COST_USD], "0.0011")
        self.assertEqual(tool.parent_span_id, spans[0].span_id)

    def test_no_cost_attribute_when_unpriced(self) -> None:
        spans = capture_spans([_d("bot", "open_pr", 80, 10, 3)], "bot")
        self.assertNotIn(COST_USD, spans[1].attributes)

    def test_deterministic_and_empty(self) -> None:
        traces = [_d("a", "t", 9, 1, 1)]
        self.assertEqual(capture_spans(traces, "a"), capture_spans(traces, "a"))
        self.assertEqual(capture_spans([], "a"), [])

    def test_otlp_envelope(self) -> None:
        doc = to_otlp(capture_spans([_d("bot", "read_repo", 100, 10, 5)], "bot"))
        spans = doc["resourceSpans"][0]["scopeSpans"][0]["spans"]
        self.assertEqual(len(spans), 2)
        # The usage attribute key is present on the OTLP span.
        keys = {a["key"] for a in spans[1]["attributes"]}
        self.assertIn(USAGE_INPUT, keys)


if __name__ == "__main__":
    unittest.main()
