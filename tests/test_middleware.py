"""Gateway middleware pipeline: observe + fail-safe deny, never allow (I2).

Uses the real catalog + Gateway. A middleware can deny early or observe the
outcome; it cannot turn a policy decision into an allow.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from recette.platform.catalog import load_catalog
from recette.platform.events import ApprovalState, EventKind, PolicyVerdict
from recette.platform.eventstore.memory_store import InMemoryEventStore
from recette.platform.gateway import ActionRequest, AgentResolver, Gateway
from recette.platform.ids import SequenceIdGenerator
from recette.platform.middleware import (
    DenyListMiddleware,
    MiddlewarePipeline,
    RecordingMiddleware,
)
from recette.platform.policy.model import baseline_from_catalog
from recette.platform.policy.store import PolicyStore
from recette.platform.proxy.protocol import ExecutionResult, side_effect_hash

AGENTS = {
    "admin": {"id": "admin", "role": "tool_operator", "capability_scope": ["mcp"]},
}


class _RecordingProxy:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def execute(self, event):  # type: ignore[no-untyped-def]
        self.calls.append(f"{event.target_system}/{event.action_type}")
        response = {"ok": True}
        return ExecutionResult(
            ok=True,
            status_code=200,
            response=response,
            side_effect_hash=side_effect_hash(
                event.target_system, event.action_type, event.resource, response
            ),
        )


def _invoke(agent_id: str = "admin") -> ActionRequest:
    return ActionRequest(
        agent_id=agent_id,
        action_type="invoke_tool",
        target_system="mcp",
        resource="mcp/server",
        payload={"tool": "x"},
        timestamp="2026-06-13T10:00:00Z",
    )


class _Harness:
    def __init__(self, pipeline: MiddlewarePipeline | None) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        catalog = load_catalog()
        store = PolicyStore(Path(self._tmp.name))
        store.publish(baseline_from_catalog(catalog, version="v-test"))
        self.events = InMemoryEventStore()
        self.proxy = _RecordingProxy()
        self.gateway = Gateway(
            catalog=catalog,
            policy_store=store,
            event_store=self.events,
            proxy=self.proxy,
            id_generator=SequenceIdGenerator(),
            agent_resolver=AgentResolver(lambda a: AGENTS.get(a)),
            middleware=pipeline,
        )

    def close(self) -> None:
        self._tmp.cleanup()


class TestMiddleware(unittest.TestCase):
    def test_recording_observes_without_changing_outcome(self) -> None:
        rec = RecordingMiddleware()
        h = _Harness(MiddlewarePipeline([rec]))
        try:
            outcome = h.gateway.submit(_invoke())
            # invoke_tool on mcp escalates (governed) -- middleware did not change it.
            self.assertEqual(outcome.verdict, PolicyVerdict.ESCALATE)
            self.assertEqual(rec.before_seen, [("admin", "mcp", "invoke_tool")])
            self.assertEqual(rec.after_seen, [("invoke_tool", str(PolicyVerdict.ESCALATE))])
        finally:
            h.close()

    def test_deny_list_short_circuits_before_policy(self) -> None:
        h = _Harness(MiddlewarePipeline([DenyListMiddleware(["mcp"])]))
        try:
            outcome = h.gateway.submit(_invoke())
            self.assertEqual(outcome.verdict, PolicyVerdict.DENY)
            self.assertEqual(h.proxy.calls, [])  # never executed
            self.assertEqual(len(h.events.read_from(kind=EventKind.ACTION_DENIED)), 1)
        finally:
            h.close()

    def test_raising_middleware_denies_fail_safe(self) -> None:
        class _Boom:
            def before(self, request):  # type: ignore[no-untyped-def]
                raise RuntimeError("kaboom")

            def after(self, request, outcome):  # type: ignore[no-untyped-def]
                return None

        h = _Harness(MiddlewarePipeline([_Boom()]))
        try:
            outcome = h.gateway.submit(_invoke())
            self.assertEqual(outcome.verdict, PolicyVerdict.DENY)  # fail-safe, never allow
            self.assertEqual(h.proxy.calls, [])
        finally:
            h.close()

    def test_no_middleware_is_unchanged(self) -> None:
        h = _Harness(None)
        try:
            outcome = h.gateway.submit(_invoke())
            self.assertEqual(outcome.verdict, PolicyVerdict.ESCALATE)
            self.assertEqual(outcome.approval_state, ApprovalState.PENDING)
        finally:
            h.close()


if __name__ == "__main__":
    unittest.main()
