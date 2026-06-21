"""Export-on-rotate for the bounded debug rings (long-run packet retention).

A long run drops its earliest traces/flows (deque maxlen). When a rotate dir is
configured, the entry ABOUT TO BE EVICTED is appended as a JSONL line to a
rotating file BEFORE the deque drops it, so early packets are retained. The sink
is fail-safe (IO errors swallowed -- persistence must never break the debug
path) and is a debug convenience only: the append-only audit log remains the
durable truth (I1).
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from recette.platform.events import PlatformActionEvent
from recette.platform.proxy.protocol import ExecutionResult
from recette.platform.proxy.tracing import RingTraceRecorder
from recette.platform.proxy.wire import WireFlowRecorder


def _flow(seq_path: str) -> dict:
    return {
        "method": "POST",
        "scheme": "http",
        "host": "127.0.0.1",
        "port": 9101,
        "path": seq_path,
        "status_code": 200,
        "content_type": "application/json",
        "request_body": "{}",
        "response_body": "{}",
        "run_id": "r1",
    }


def _event(event_id: str, resource: str) -> PlatformActionEvent:
    return PlatformActionEvent(
        event_id=event_id,
        timestamp="2026-06-13T00:00:00Z",
        agent_id="agent-x",
        capability_scope=(),
        role="reader",
        action_type="read_repo",
        target_system="github",
        resource=resource,
        payload={"ref": "main"},
        risk_score=1,
        risk_level="low",
    )


class WireRingPersistenceTest(unittest.TestCase):
    def test_wire_recorder_exports_evicted_entry(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            rec = WireFlowRecorder(capacity=2, rotate_dir=Path(d))
            rec.record(_flow("/a"))
            rec.record(_flow("/b"))
            rec.record(_flow("/c"))
            # ring holds last 2 (/b,/c); the evicted /a was written to the rotate file
            paths = list(Path(d).glob("*.jsonl"))
            self.assertEqual(len(paths), 1)
            lines = [json.loads(x) for x in paths[0].read_text().splitlines() if x.strip()]
            self.assertEqual(len(lines), 1)
            self.assertEqual(lines[0]["path"], "/a")
            self.assertEqual([f.to_dict()["path"] for f in rec.snapshot()], ["/b", "/c"])

    def test_no_rotate_dir_no_file_no_error(self) -> None:
        rec = WireFlowRecorder(capacity=1)
        rec.record(_flow("/a"))
        rec.record(_flow("/b"))  # evicts /a, no sink -> fine
        self.assertEqual([f.to_dict()["path"] for f in rec.snapshot()], ["/b"])


class TraceRingPersistenceTest(unittest.TestCase):
    def test_trace_recorder_exports_evicted_entry(self) -> None:
        ok = ExecutionResult(ok=True, status_code=200)
        with tempfile.TemporaryDirectory() as d:
            rec = RingTraceRecorder(capacity=2, rotate_dir=Path(d))
            rec.record(_event("evt-0001", "acme/a"), ok)
            rec.record(_event("evt-0002", "acme/b"), ok)
            rec.record(_event("evt-0003", "acme/c"), ok)
            # ring holds the last 2; the evicted first trace was written out.
            paths = list(Path(d).glob("*.jsonl"))
            self.assertEqual(len(paths), 1)
            lines = [json.loads(x) for x in paths[0].read_text().splitlines() if x.strip()]
            self.assertEqual(len(lines), 1)
            self.assertEqual(lines[0]["event_id"], "evt-0001")
            self.assertEqual([t.event_id for t in rec.snapshot()], ["evt-0002", "evt-0003"])

    def test_no_rotate_dir_no_error(self) -> None:
        ok = ExecutionResult(ok=True, status_code=200)
        rec = RingTraceRecorder(capacity=1)
        rec.record(_event("evt-0001", "acme/a"), ok)
        rec.record(_event("evt-0002", "acme/b"), ok)  # evicts first, no sink -> fine
        self.assertEqual([t.event_id for t in rec.snapshot()], ["evt-0002"])


if __name__ == "__main__":
    unittest.main()
