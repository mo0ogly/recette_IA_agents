"""OpenTelemetry GenAI export of a recette run -- deterministic (I4), read-only (I1).

The attribute/operation names are the canonical GenAI semantic conventions
(microsoft/agent-framework observability.py): invoke_agent / execute_tool spans
with gen_ai.* attributes. Dependency-free, no wall clock.
"""

from __future__ import annotations

import unittest

from recette.events import AgentAction
from recette.llm import LlmDecision
from recette.maf_orchestration import HandoffHop, OrchestrationRun, ToolCall
from recette.otel import (
    AGENT_ID,
    AGENT_NAME,
    APPROVED,
    DECISION,
    GOAL,
    OP,
    OP_EXECUTE_TOOL,
    OP_INVOKE_AGENT,
    RESOURCE,
    TARGET_SYSTEM,
    TOOL_ARGS,
    TOOL_NAME,
    action_log_spans,
    orchestration_spans,
    recording_spans,
    to_otlp,
)
from recette.recording import RecordedStep, Recording

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


def _action(seq: int, action_type: str, mode: str, resource: str, approved: bool) -> AgentAction:
    return AgentAction(
        event_id=f"ev-{seq}",
        seq=seq,
        timestamp="1970-01-01T00:00:00Z",
        agent_id="git-bot",
        principal="ci-bot",
        target_system="github",
        action_type=action_type,
        mode=mode,
        resource=resource,
        approved=approved,
    )


ACTION_LOG = [
    _action(1, "read_repo", "read", "acme/widgets", False),
    _action(2, "merge_pr", "write", "acme/widgets#42", True),
]


class TestActionLogSpans(unittest.TestCase):
    def test_root_invoke_agent_then_execute_tool_per_action(self) -> None:
        spans = action_log_spans(ACTION_LOG)
        # root invoke_agent + one execute_tool per action.
        self.assertEqual(len(spans), 3)
        root = spans[0]
        self.assertEqual(root.parent_span_id, "")
        self.assertEqual(root.attributes[OP], OP_INVOKE_AGENT)
        self.assertEqual(root.attributes[AGENT_NAME], "git-bot")

        read, merge = spans[1], spans[2]
        self.assertEqual(read.attributes[OP], OP_EXECUTE_TOOL)
        self.assertEqual(read.attributes[TOOL_NAME], "read_repo")
        self.assertEqual(read.name, "execute_tool read_repo")
        self.assertEqual(read.parent_span_id, root.span_id)
        # inspect_ia_agents-only AgentActionEvent fields ride along as inspect_ia_agents.* attrs.
        self.assertEqual(merge.attributes[TARGET_SYSTEM], "github")
        self.assertEqual(merge.attributes[RESOURCE], "acme/widgets#42")
        self.assertEqual(merge.attributes[APPROVED], 1)
        self.assertEqual(read.attributes[APPROVED], 0)
        self.assertEqual(merge.attributes[AGENT_ID], "git-bot")

    def test_empty_log_yields_no_spans(self) -> None:
        self.assertEqual(action_log_spans([]), [])

    def test_export_is_deterministic_and_read_only(self) -> None:
        self.assertEqual(
            to_otlp(action_log_spans(ACTION_LOG)),
            to_otlp(action_log_spans(ACTION_LOG)),
        )
        # I1: the source rows are untouched.
        self.assertEqual([a.seq for a in ACTION_LOG], [1, 2])


class TestRecordingSpansWhy(unittest.TestCase):
    """The legibility 'why': goal on the root, intent (tool_args) + decision text
    on each tool span. Read from the persisted recording, deterministic (I4)."""

    def _recording(self) -> Recording:
        rec = Recording(
            agent_id="pay-bot",
            principal="ci-bot",
            target_system="finance",
            goal="Process the weekly accounts-payable run",
            provider="stub",
        )
        rec.steps = [
            RecordedStep(
                decision=LlmDecision(
                    kind="tool_call",
                    text="invoice looks valid, paying",
                    tool_name="create_payment",
                    tool_args={"resource": "inv/v1", "amount": 100},
                ),
                action={
                    "action_type": "create_payment",
                    "seq": 1,
                    "agent_id": "pay-bot",
                    "target_system": "finance",
                    "principal": "ci-bot",
                    "mode": "write",
                    "resource": "inv/v1",
                    "approved": True,
                },
            ),
        ]
        return rec

    def test_goal_on_root_and_intent_plus_decision_on_tool_span(self) -> None:
        spans = recording_spans(self._recording(), "rec-why-1")
        root, tool = spans[0], spans[1]
        self.assertEqual(root.attributes[GOAL], "Process the weekly accounts-payable run")
        self.assertEqual(tool.attributes[DECISION], "invoice looks valid, paying")
        # tool args are JSON with sorted keys (deterministic intent string).
        self.assertEqual(tool.attributes[TOOL_ARGS], '{"amount": 100, "resource": "inv/v1"}')

    def test_deterministic(self) -> None:
        a = to_otlp(recording_spans(self._recording(), "rec-why-1"))
        b = to_otlp(recording_spans(self._recording(), "rec-why-1"))
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
