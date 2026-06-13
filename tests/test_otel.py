"""OpenTelemetry GenAI export of a recette run -- deterministic (I4), read-only (I1).

The attribute/operation names are the canonical GenAI semantic conventions
(microsoft/agent-framework observability.py): invoke_agent / execute_tool spans
with gen_ai.* attributes. Dependency-free, no wall clock.
"""

from __future__ import annotations

import unittest

from recette.maf_orchestration import HandoffHop, OrchestrationRun, ToolCall
from recette.otel import (
    AGENT_NAME,
    OP,
    OP_EXECUTE_TOOL,
    OP_INVOKE_AGENT,
    TOOL_NAME,
    orchestration_spans,
    to_otlp,
)

TEAM = {
    "kind": "maf_orchestration",
    "agent_id": "otel-team",
    "name": "Otel Team",
    "start_agent": "triage",
    "participants": [
        {
            "agent_id": "triage",
            "declared_identity": {"provider": "AzureOpenAI", "model": "m"},
            "handoffs": [{"target": "worker"}],
        },
        {
            "agent_id": "worker",
            "declared_identity": {"provider": "AzureOpenAI", "model": "m"},
            "tools": [{"tool_kind": "mcp", "target": "mcp://x", "approval": "always"}],
        },
    ],
}

RUN = OrchestrationRun(
    hops=[HandoffHop(1, "triage", "worker")],
    calls=[ToolCall(1, "worker", "AzureOpenAI", "m", "mcp://x", "mcp", approved=True)],
)


class TestOrchestrationSpans(unittest.TestCase):
    def test_root_and_children_with_genai_attributes(self) -> None:
        spans = orchestration_spans(TEAM, RUN)
        # root invoke_agent + one routed invoke_agent (worker) + one execute_tool.
        self.assertEqual(len(spans), 3)
        root = spans[0]
        self.assertEqual(root.parent_span_id, "")
        self.assertEqual(root.attributes[OP], OP_INVOKE_AGENT)
        self.assertTrue(root.name.startswith("invoke_agent "))

        routed = spans[1]
        self.assertEqual(routed.attributes[OP], OP_INVOKE_AGENT)
        self.assertEqual(routed.attributes[AGENT_NAME], "worker")
        self.assertEqual(routed.parent_span_id, root.span_id)
        self.assertEqual(routed.attributes["gen_ai.provider.name"], "AzureOpenAI")

        tool = spans[2]
        self.assertEqual(tool.attributes[OP], OP_EXECUTE_TOOL)
        self.assertEqual(tool.attributes[TOOL_NAME], "mcp")
        self.assertEqual(tool.name, "execute_tool mcp")

    def test_export_is_deterministic(self) -> None:
        # Same run -> byte-identical OTLP (no wall clock, no random ids).
        self.assertEqual(
            to_otlp(orchestration_spans(TEAM, RUN)),
            to_otlp(orchestration_spans(TEAM, RUN)),
        )

    def test_otlp_shape(self) -> None:
        otlp = to_otlp(orchestration_spans(TEAM, RUN))
        rs = otlp["resourceSpans"][0]
        spans = rs["scopeSpans"][0]["spans"]
        self.assertEqual(len(spans), 3)
        # Every span carries a trace id and a name; attributes are key/value pairs.
        for s in spans:
            self.assertTrue(s["traceId"])
            self.assertTrue(s["name"])
            self.assertIn("attributes", s)
        # gen_ai.operation.name present as a stringValue attribute on the root.
        ops = {a["key"]: a["value"] for a in spans[0]["attributes"]}
        self.assertEqual(ops[OP], {"stringValue": OP_INVOKE_AGENT})

    def test_export_does_not_mutate_the_run(self) -> None:
        before = (len(RUN.hops), len(RUN.calls))
        orchestration_spans(TEAM, RUN)
        self.assertEqual((len(RUN.hops), len(RUN.calls)), before)  # I1: read-only

    def test_order_style_routes_each_participant(self) -> None:
        team = {
            "kind": "maf_orchestration",
            "style": "sequential",
            "agent_id": "seq-otel",
            "name": "Seq",
            "participants": [
                {"agent_id": "a", "declared_identity": {"provider": "P", "model": "m"}},
                {"agent_id": "b", "declared_identity": {"provider": "P", "model": "m"}},
            ],
        }
        spans = orchestration_spans(team, OrchestrationRun(order=["a", "b"]))
        names = [s.attributes.get(AGENT_NAME) for s in spans]
        self.assertEqual(names, ["seq-otel", "a", "b"])  # root + 2 routed


if __name__ == "__main__":
    unittest.main()
