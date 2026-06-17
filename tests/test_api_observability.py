"""WS-C: observability traces/spans router renders a deterministic span tree.

The router is a read-only projection of persisted recordings into GenAI spans
(I1: never mutates; I4: same recording -> identical spans).
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:  # pragma: no cover - exercised only when fastapi is installed
    from fastapi.testclient import TestClient

    from recette.api.app import create_app
    from recette.api.campaign_store import RecordingStore

    _HAVE_FASTAPI = True
except ImportError:  # pragma: no cover
    _HAVE_FASTAPI = False

from recette.llm import LlmDecision
from recette.otel import _trace_id, recording_spans
from recette.recording import RecordedStep, Recording


def _recording() -> Recording:
    rec = Recording(
        agent_id="gh-pr-bot",
        principal="bot@acme",
        target_system="github",
        goal="open a PR",
        provider="stub",
    )
    rec.steps = [
        RecordedStep(
            decision=LlmDecision(kind="tool_call", tool_name="read_repo", tool_args={}),
            action={
                "event_id": "evt-0001",
                "seq": 1,
                "agent_id": "gh-pr-bot",
                "principal": "bot@acme",
                "target_system": "github",
                "action_type": "read_repo",
                "mode": "read",
                "resource": "acme/x",
                "approved": False,
            },
        ),
        RecordedStep(decision=LlmDecision(kind="final", text="done")),
    ]
    return rec


class TestRecordingSpans(unittest.TestCase):
    def test_root_plus_one_span_per_action_and_deterministic(self) -> None:
        rec = _recording()
        spans = recording_spans(rec, "rec-1")
        # root invoke_agent + one execute_tool (the final step has no action).
        self.assertEqual(len(spans), 2)
        self.assertEqual(spans[0].parent_span_id, "")
        self.assertEqual(spans[1].parent_span_id, spans[0].span_id)
        self.assertIn("execute_tool read_repo", spans[1].name)
        # Determinism (I4): same input -> identical ids.
        self.assertEqual(
            [s.span_id for s in spans], [s.span_id for s in recording_spans(rec, "rec-1")]
        )


@unittest.skipUnless(_HAVE_FASTAPI, "fastapi not installed")
class TestObservabilityRouter(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        store = RecordingStore(Path(self._tmp.name))
        store.save("rec-1", _recording())
        self.client = TestClient(create_app(recording_store=store))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_list_traces(self) -> None:
        rows = self.client.get("/observability/traces").json()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["recording_id"], "rec-1")
        self.assertEqual(rows[0]["trace_id"], _trace_id("rec-1"))
        self.assertEqual(rows[0]["span_count"], 2)  # 1 action + root

    def test_get_trace_span_tree(self) -> None:
        tid = _trace_id("rec-1")
        body = self.client.get(f"/observability/traces/{tid}").json()
        self.assertEqual(body["recording_id"], "rec-1")
        self.assertEqual(len(body["spans"]), 2)
        self.assertEqual(body["spans"][0]["parent_span_id"], "")
        self.assertEqual(body["spans"][1]["duration_nano"], 1_000_000)

    def test_get_trace_unknown_is_404(self) -> None:
        self.assertEqual(self.client.get("/observability/traces/deadbeef").status_code, 404)

    def test_get_span_detail_and_404(self) -> None:
        tid = _trace_id("rec-1")
        spans = self.client.get(f"/observability/traces/{tid}").json()["spans"]
        sid = spans[1]["span_id"]
        detail = self.client.get(f"/observability/spans/{sid}").json()
        self.assertEqual(detail["span_id"], sid)
        self.assertEqual(self.client.get("/observability/spans/nope").status_code, 404)


if __name__ == "__main__":
    unittest.main()
