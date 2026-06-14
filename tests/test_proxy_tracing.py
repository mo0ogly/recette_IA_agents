# tests/test_proxy_tracing.py
"""S1: debug tracing for the side-effect proxy (I5 observability).

TracingProxy decorates any ExternalSystemProxy: it records one ProxyTrace per
execute() when enabled, returns the wrapped result verbatim, never raises on a
recording failure, and is a no-op when disabled. RingTraceRecorder is bounded,
monotone-ordered (I4) and immutable-by-view (I1).
"""

from __future__ import annotations

import unittest

from recette.platform.events import PlatformActionEvent
from recette.platform.proxy.protocol import ExecutionResult
from recette.platform.proxy.tracing import (
    RingTraceRecorder,
    TracingProxy,
    debug_enabled_from_env,
)


def _event(event_id: str = "evt-0001", action_type: str = "read_repo") -> PlatformActionEvent:
    return PlatformActionEvent(
        event_id=event_id,
        timestamp="2026-06-13T00:00:00Z",
        agent_id="agent-x",
        capability_scope=(),
        role="reader",
        action_type=action_type,
        target_system="github",
        resource="acme/widgets",
        payload={"ref": "main"},
        risk_score=1,
        risk_level="low",
    )


class _StubProxy:
    """ExternalSystemProxy stub returning a fixed result; counts calls."""

    def __init__(self, result: ExecutionResult) -> None:
        self._result = result
        self.calls = 0

    def execute(self, event: PlatformActionEvent) -> ExecutionResult:
        self.calls += 1
        return self._result


class _BoomRecorder:
    """Recorder whose record() always raises -- proves fail-safe swallowing."""

    def record(self, event, result) -> None:  # noqa: ANN001
        raise RuntimeError("recorder down")

    def snapshot(self):  # noqa: ANN201
        return []


class TracingProxyTests(unittest.TestCase):
    def test_records_one_trace_per_execute_when_enabled(self) -> None:
        ok = ExecutionResult(ok=True, status_code=200, response={"x": 1}, side_effect_hash="h1")
        recorder = RingTraceRecorder()
        proxy = TracingProxy(_StubProxy(ok), recorder, enabled=True)
        proxy.execute(_event("evt-0001"))
        proxy.execute(_event("evt-0002"))
        traces = recorder.snapshot()
        self.assertEqual([t.event_id for t in traces], ["evt-0001", "evt-0002"])
        self.assertEqual([t.seq for t in traces], [1, 2])
        self.assertTrue(traces[0].ok)
        self.assertEqual(traces[0].side_effect_hash, "h1")
        self.assertEqual(traces[0].request_payload, {"ref": "main"})
        # The server response body is captured (the other half of the exchange),
        # and surfaced in to_dict so the console can show the full round-trip.
        self.assertEqual(traces[0].response, {"x": 1})
        self.assertEqual(traces[0].to_dict()["response"], {"x": 1})

    def test_tags_traces_with_run_id_when_provided(self) -> None:
        # F3: a TracingProxy bound to a run stamps every trace with that run_id,
        # so the console can filter the global ring down to one run.
        ok = ExecutionResult(ok=True, status_code=200, side_effect_hash="h1")
        recorder = RingTraceRecorder()
        proxy = TracingProxy(_StubProxy(ok), recorder, enabled=True, run_id="run-abc")
        proxy.execute(_event("evt-0001"))
        trace = recorder.snapshot()[0]
        self.assertEqual(trace.run_id, "run-abc")
        self.assertEqual(trace.to_dict()["run_id"], "run-abc")

    def test_run_id_defaults_to_none(self) -> None:
        ok = ExecutionResult(ok=True, status_code=200)
        recorder = RingTraceRecorder()
        TracingProxy(_StubProxy(ok), recorder, enabled=True).execute(_event())
        self.assertIsNone(recorder.snapshot()[0].run_id)

    def test_returns_wrapped_result_verbatim(self) -> None:
        ok = ExecutionResult(ok=True, status_code=201, response={"created": True})
        proxy = TracingProxy(_StubProxy(ok), RingTraceRecorder(), enabled=True)
        result = proxy.execute(_event())
        self.assertIs(result.ok, True)
        self.assertEqual(result.status_code, 201)
        self.assertEqual(result.response, {"created": True})

    def test_disabled_is_a_noop_and_still_calls_inner(self) -> None:
        ok = ExecutionResult(ok=True, status_code=200)
        inner = _StubProxy(ok)
        recorder = RingTraceRecorder()
        proxy = TracingProxy(inner, recorder, enabled=False)
        result = proxy.execute(_event())
        self.assertIs(result.ok, True)
        self.assertEqual(inner.calls, 1)
        self.assertEqual(recorder.snapshot(), [])

    def test_records_failures_too(self) -> None:
        fail = ExecutionResult(ok=False, status_code=503, error="lab returned HTTP 503")
        recorder = RingTraceRecorder()
        proxy = TracingProxy(_StubProxy(fail), recorder, enabled=True)
        proxy.execute(_event())
        trace = recorder.snapshot()[0]
        self.assertFalse(trace.ok)
        self.assertEqual(trace.status_code, 503)
        self.assertEqual(trace.error, "lab returned HTTP 503")
        self.assertIsNone(trace.side_effect_hash)

    def test_recording_failure_never_breaks_execution(self) -> None:
        ok = ExecutionResult(ok=True, status_code=200)
        inner = _StubProxy(ok)
        proxy = TracingProxy(inner, _BoomRecorder(), enabled=True)
        # Must not raise even though the recorder explodes.
        result = proxy.execute(_event())
        self.assertIs(result.ok, True)
        self.assertEqual(inner.calls, 1)


class RingTraceRecorderTests(unittest.TestCase):
    def test_capacity_must_be_positive(self) -> None:
        with self.assertRaises(ValueError):
            RingTraceRecorder(capacity=0)

    def test_bounded_drops_oldest_but_seq_stays_monotone(self) -> None:
        recorder = RingTraceRecorder(capacity=2)
        ok = ExecutionResult(ok=True, status_code=200)
        for i in range(1, 5):
            recorder.record(_event(f"evt-{i:04d}"), ok)
        traces = recorder.snapshot()
        # Ring kept only the last 2, but their seq reflects the true global order.
        self.assertEqual([t.event_id for t in traces], ["evt-0003", "evt-0004"])
        self.assertEqual([t.seq for t in traces], [3, 4])

    def test_snapshot_is_a_copy_not_the_live_ring(self) -> None:
        recorder = RingTraceRecorder()
        ok = ExecutionResult(ok=True, status_code=200)
        recorder.record(_event(), ok)
        snap = recorder.snapshot()
        snap.clear()
        self.assertEqual(len(recorder.snapshot()), 1)

    def test_clear_empties_the_ring(self) -> None:
        recorder = RingTraceRecorder()
        recorder.record(_event(), ExecutionResult(ok=True, status_code=200))
        recorder.clear()
        self.assertEqual(recorder.snapshot(), [])


class DebugEnvTests(unittest.TestCase):
    def test_truthy_values(self) -> None:
        import os

        for val, expected in [
            ("1", True),
            ("true", True),
            ("ON", True),
            ("yes", True),
            ("0", False),
            ("", False),
            ("nope", False),
        ]:
            os.environ["INSPECT_IA_AGENTS_PROXY_DEBUG"] = val
            self.assertEqual(debug_enabled_from_env(), expected, val)
        del os.environ["INSPECT_IA_AGENTS_PROXY_DEBUG"]
        self.assertFalse(debug_enabled_from_env())


if __name__ == "__main__":
    unittest.main()
