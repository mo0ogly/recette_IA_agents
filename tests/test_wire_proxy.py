"""Unit tests for the wire-proxy core (recette/platform/proxy/wire.py).

Deterministic, container-free: the recorder and normalizer are pure, so the full
ingest -> normalize -> ring path is exercised without a live mitmproxy overlay.
"""

from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError

from recette.platform.proxy.wire import (
    MAX_BODY_CHARS,
    TRUNCATION_MARKER,
    WireFlow,
    WireFlowRecorder,
    normalize_flow,
)


def _payload(**over: object) -> dict:
    base = {
        "method": "post",
        "scheme": "http",
        "host": "localhost",
        "port": 8082,
        "path": "/github/execute",
        "status_code": 200,
        "content_type": "application/json",
        "request_body": '{"action_type":"open_pr"}',
        "response_body": '{"success":true}',
    }
    base.update(over)
    return base


class NormalizeFlowTests(unittest.TestCase):
    def test_normalizes_a_well_formed_payload(self) -> None:
        flow = normalize_flow(_payload(), seq=1)
        self.assertEqual(flow.seq, 1)
        self.assertEqual(flow.method, "POST")  # upper-cased
        self.assertEqual(flow.host, "localhost")
        self.assertEqual(flow.port, 8082)
        self.assertTrue(flow.ok)

    def test_status_zero_is_not_ok(self) -> None:
        # No response (connect failure) must never badge "ok".
        flow = normalize_flow(_payload(status_code=0), seq=1)
        self.assertFalse(flow.ok)

    def test_status_4xx_is_not_ok(self) -> None:
        flow = normalize_flow(_payload(status_code=403), seq=1)
        self.assertFalse(flow.ok)

    def test_non_numeric_status_and_port_default_to_zero(self) -> None:
        flow = normalize_flow(_payload(status_code="nope", port="x"), seq=1)
        self.assertEqual(flow.status_code, 0)
        self.assertEqual(flow.port, 0)
        self.assertFalse(flow.ok)

    def test_missing_fields_get_safe_defaults(self) -> None:
        flow = normalize_flow({}, seq=7)
        self.assertEqual(flow.seq, 7)
        self.assertEqual(flow.method, "")
        self.assertEqual(flow.host, "")
        self.assertEqual(flow.status_code, 0)
        self.assertEqual(flow.request_body, "")
        self.assertIsNone(flow.run_id)

    def test_run_id_kept_only_when_nonempty_string(self) -> None:
        self.assertEqual(normalize_flow(_payload(run_id="run-42"), seq=1).run_id, "run-42")
        self.assertIsNone(normalize_flow(_payload(run_id=""), seq=1).run_id)
        self.assertIsNone(normalize_flow(_payload(run_id=123), seq=1).run_id)

    def test_oversized_body_is_truncated_with_marker(self) -> None:
        big = "x" * (MAX_BODY_CHARS + 100)
        flow = normalize_flow(_payload(response_body=big), seq=1)
        self.assertTrue(flow.response_body.endswith(TRUNCATION_MARKER))
        self.assertEqual(len(flow.response_body), MAX_BODY_CHARS + len(TRUNCATION_MARKER))

    def test_non_dict_payload_raises(self) -> None:
        with self.assertRaises(ValueError):
            normalize_flow(["not", "a", "dict"], seq=1)  # type: ignore[arg-type]

    def test_to_dict_is_round_trippable(self) -> None:
        d = normalize_flow(_payload(), seq=3).to_dict()
        self.assertEqual(d["seq"], 3)
        self.assertEqual(d["method"], "POST")
        self.assertIn("response_body", d)


class WireFlowRecorderTests(unittest.TestCase):
    def test_record_assigns_monotone_seq(self) -> None:
        rec = WireFlowRecorder()
        f1 = rec.record(_payload())
        f2 = rec.record(_payload())
        self.assertEqual((f1.seq, f2.seq), (1, 2))
        self.assertEqual([f.seq for f in rec.snapshot()], [1, 2])

    def test_ring_is_bounded_and_keeps_newest(self) -> None:
        rec = WireFlowRecorder(capacity=2)
        rec.record(_payload(path="/a"))
        rec.record(_payload(path="/b"))
        rec.record(_payload(path="/c"))
        snap = rec.snapshot()
        self.assertEqual(len(snap), 2)
        self.assertEqual([f.path for f in snap], ["/b", "/c"])
        # seq stays monotone even after the ring wrapped.
        self.assertEqual([f.seq for f in snap], [2, 3])

    def test_clear_empties_the_ring(self) -> None:
        rec = WireFlowRecorder()
        rec.record(_payload())
        rec.clear()
        self.assertEqual(rec.snapshot(), [])

    def test_zero_capacity_rejected(self) -> None:
        with self.assertRaises(ValueError):
            WireFlowRecorder(capacity=0)

    def test_snapshot_is_a_copy(self) -> None:
        rec = WireFlowRecorder()
        rec.record(_payload())
        snap = rec.snapshot()
        snap.clear()
        self.assertEqual(len(rec.snapshot()), 1)

    def test_stored_flow_is_immutable(self) -> None:
        rec = WireFlowRecorder()
        flow = rec.record(_payload())
        self.assertIsInstance(flow, WireFlow)
        with self.assertRaises(FrozenInstanceError):
            flow.status_code = 500  # type: ignore[misc]  # frozen dataclass


if __name__ == "__main__":
    unittest.main()
