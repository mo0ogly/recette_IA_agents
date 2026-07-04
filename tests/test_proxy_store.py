# tests/test_proxy_store.py
"""Task 1: SQLite-backed proxy trace store (debug observability buffer).

SqliteProxyStore owns the connection + schema (traces AND wire tables, wire is
filled by Task 2). SqliteTraceRecorder is a facade implementing the
TraceRecorder protocol: record() never raises (fail-safe, I5 path), snapshot()
rebuilds ProxyTrace field-for-field identical to RingTraceRecorder, clear()
empties the debug buffer only (never the audit log, I1) while seq stays
monotone (sqlite AUTOINCREMENT keeps the counter across DELETE).
"""

from __future__ import annotations

import dataclasses
import os
import tempfile
import threading
import unittest
from pathlib import Path

from recette.platform.events import PlatformActionEvent
from recette.platform.proxy.protocol import ExecutionResult
from recette.platform.proxy.reconcile import wire_flow_side_effect_hash
from recette.platform.proxy.store import (
    DB_PATH_ENV,
    DEFAULT_DB_PATH,
    DEFAULT_MAX_ROWS,
    MAX_ROWS_ENV,
    SqliteProxyStore,
    SqliteTraceRecorder,
    SqliteWireRecorder,
    db_path_from_env,
    max_rows_from_env,
)
from recette.platform.proxy.tracing import ProxyTrace, RingTraceRecorder
from recette.platform.proxy.wire import WireFlow, WireFlowRecorder


def _event(
    event_id: str = "evt-0001",
    action_type: str = "read_repo",
    agent_id: str = "agent-x",
) -> PlatformActionEvent:
    return PlatformActionEvent(
        event_id=event_id,
        timestamp="2026-06-13T00:00:00Z",
        agent_id=agent_id,
        capability_scope=(),
        role="reader",
        action_type=action_type,
        target_system="github",
        resource="acme/widgets",
        payload={"ref": "main"},
        risk_score=1,
        risk_level="low",
    )


class _BrokenConn:
    """Connection double whose every call raises -- proves fail-safe record()."""

    def execute(self, *args: object, **kwargs: object) -> None:
        raise RuntimeError("db down")

    def commit(self) -> None:
        raise RuntimeError("db down")

    def fetchall(self, *args: object, **kwargs: object) -> None:
        raise RuntimeError("db down")

    def executescript(self, *args: object, **kwargs: object) -> None:
        raise RuntimeError("db down")

    def close(self, *args: object, **kwargs: object) -> None:
        raise RuntimeError("db down")


def _governed_wire_payload(run_id: str | None = "run-abc") -> dict:
    # Governed-action shape: POST /{target_system}/execute with JSON bodies
    # (same shape as tests/test_api_wire_session_hash.py).
    return {
        "method": "POST",
        "scheme": "http",
        "host": "127.0.0.1",
        "port": 9101,
        "path": "/github/execute",
        "status_code": 200,
        "content_type": "application/json",
        "request_body": (
            '{"event_id":"e1","action_type":"read_repo","resource":"acme/x","payload":{}}'
        ),
        "response_body": '{"data":{"action":"read_repo","resource":"acme/x"},"success":true}',
        "run_id": run_id,
    }


def _health_wire_payload() -> dict:
    # Non-governed traffic (no /{ts}/execute path): benign, never hashed.
    return {
        "method": "GET",
        "scheme": "http",
        "host": "127.0.0.1",
        "port": 8082,
        "path": "/health",
        "status_code": 200,
        "content_type": "application/json",
        "request_body": "",
        "response_body": '{"ok":true}',
        "run_id": None,
    }


class SqliteTraceRecorderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = SqliteProxyStore(":memory:")
        self.recorder = SqliteTraceRecorder(self.store)

    def tearDown(self) -> None:
        self.store.close()

    def test_record_three_snapshot_identical_to_ring(self) -> None:
        ok = ExecutionResult(
            ok=True,
            status_code=200,
            response={"x": 1},
            side_effect_hash="h1",
            target="api.github.com",
        )
        ring = RingTraceRecorder()
        for i in range(1, 4):
            self.recorder.record(_event(f"evt-{i:04d}"), ok, run_id="run-abc")
            ring.record(_event(f"evt-{i:04d}"), ok, run_id="run-abc")
        traces = self.recorder.snapshot()
        self.assertEqual(len(traces), 3)
        self.assertIsInstance(traces[0], ProxyTrace)
        # (a) The store owns the monotone order: seq is 1-based AUTOINCREMENT.
        self.assertEqual([t.seq for t in traces], [1, 2, 3])
        # (b) Field parity with the ring recorder. The two recorders number
        # seq independently, so compare with seq zeroed on both sides.
        self.assertEqual(
            [dataclasses.replace(t, seq=0) for t in traces],
            [dataclasses.replace(t, seq=0) for t in ring.snapshot()],
        )
        self.assertIsNone(self.recorder.store_error)
        self.assertIsNone(self.store.store_error)

    def test_target_falls_back_to_target_system(self) -> None:
        # Same fallback as RingTraceRecorder: result.target or event.target_system.
        ok = ExecutionResult(ok=True, status_code=200)
        self.recorder.record(_event(), ok)
        trace = self.recorder.snapshot()[0]
        self.assertEqual(trace.target, "github")
        self.assertIsNone(trace.run_id)

    def test_records_failures_too(self) -> None:
        fail = ExecutionResult(ok=False, status_code=503, error="lab returned HTTP 503")
        self.recorder.record(_event(), fail)
        trace = self.recorder.snapshot()[0]
        self.assertFalse(trace.ok)
        self.assertEqual(trace.status_code, 503)
        self.assertEqual(trace.error, "lab returned HTTP 503")
        self.assertIsNone(trace.side_effect_hash)

    def test_json_blobs_are_compact_and_byte_stable(self) -> None:
        # I4: the stored JSON is canonical (sorted keys, no spaces).
        ok = ExecutionResult(ok=True, status_code=200, response={"b": 2, "a": 1})
        self.recorder.record(_event(), ok)
        # Intentional private access: there is no public raw-blob API and the
        # I4 assertion needs the stored bytes, not the rebuilt dict.
        row = self.store._conn.execute(
            "SELECT request_payload, response FROM proxy_traces"
        ).fetchone()
        self.assertEqual(row[0], '{"ref":"main"}')
        self.assertEqual(row[1], '{"a":1,"b":2}')

    def test_broken_store_never_raises_and_error_clears_on_recovery(self) -> None:
        ok = ExecutionResult(ok=True, status_code=200)
        real_conn = self.store._conn
        self.store._conn = _BrokenConn()
        with self.assertLogs("recette.proxy.store", level="ERROR"):
            self.recorder.record(_event("evt-fail"), ok)  # must not raise
        self.assertEqual(self.recorder.store_error, "db down")
        self.assertEqual(self.store.store_error, "db down")
        # Recovery: restore the live connection; the next SUCCESSFUL insert
        # clears store_error back to None (the error never latches forever).
        self.store._conn = real_conn
        self.recorder.record(_event("evt-okay"), ok)
        self.assertIsNone(self.recorder.store_error)
        self.assertIsNone(self.store.store_error)
        self.assertEqual(len(self.recorder.snapshot()), 1)

    def test_concurrent_records_all_land(self) -> None:
        # 20 threads record through the SAME recorder; the store lock must
        # serialize inserts without losing or duplicating a row.
        thread_count = 20
        barrier = threading.Barrier(thread_count)
        ok = ExecutionResult(ok=True, status_code=200)

        def _record(index: int) -> None:
            barrier.wait()
            self.recorder.record(_event(f"evt-c{index:03d}"), ok)

        threads = [threading.Thread(target=_record, args=(i,)) for i in range(thread_count)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        traces = self.recorder.snapshot()
        self.assertEqual(len(traces), thread_count)
        self.assertEqual(
            {t.event_id for t in traces},
            {f"evt-c{i:03d}" for i in range(thread_count)},
        )
        self.assertIsNone(self.store.store_error)

    def test_mixed_run_id_and_agent_ids_round_trip(self) -> None:
        # Baseline for the Task 3 filters: a NULL run_id must round-trip as
        # None and a string run_id as the exact string (no "" / "None"
        # coercion), with distinct agent_ids preserved per row.
        ok = ExecutionResult(ok=True, status_code=200)
        self.recorder.record(_event("evt-0001", agent_id="agent-a"), ok)
        self.recorder.record(_event("evt-0002", agent_id="agent-b"), ok, run_id="run-x")
        self.recorder.record(_event("evt-0003", agent_id="agent-c"), ok)
        traces = self.recorder.snapshot()
        self.assertEqual([t.run_id for t in traces], [None, "run-x", None])
        self.assertEqual([t.agent_id for t in traces], ["agent-a", "agent-b", "agent-c"])

    def test_clear_empties_but_seq_stays_monotone(self) -> None:
        ok = ExecutionResult(ok=True, status_code=200)
        self.recorder.record(_event("evt-0001"), ok)
        first_seq = self.recorder.snapshot()[0].seq
        self.recorder.clear()
        self.assertEqual(self.recorder.snapshot(), [])
        self.recorder.record(_event("evt-0002"), ok)
        traces = self.recorder.snapshot()
        self.assertEqual(len(traces), 1)
        # AUTOINCREMENT retains the counter in sqlite_sequence across DELETE.
        self.assertGreater(traces[0].seq, first_seq)


class SqliteWireRecorderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = SqliteProxyStore(":memory:")
        self.recorder = SqliteWireRecorder(self.store)

    def tearDown(self) -> None:
        self.store.close()

    def test_record_three_snapshot_identical_to_ring(self) -> None:
        payloads = [
            _governed_wire_payload(),
            _health_wire_payload(),
            _governed_wire_payload(run_id=None),
        ]
        ring = WireFlowRecorder()
        returned = []
        for payload in payloads:
            returned.append(self.recorder.record(payload))
            ring.record(payload)
        flows = self.recorder.snapshot()
        self.assertEqual(len(flows), 3)
        self.assertIsInstance(flows[0], WireFlow)
        # (a) The store owns the monotone order: seq is 1-based AUTOINCREMENT,
        # both on the snapshot and on the flow returned by record().
        self.assertEqual([f.seq for f in flows], [1, 2, 3])
        self.assertEqual([f.seq for f in returned], [1, 2, 3])
        # (b) Field parity with the in-memory ring recorder. The two recorders
        # number seq independently, so compare with seq zeroed on both sides.
        self.assertEqual(
            [dataclasses.replace(f, seq=0) for f in flows],
            [dataclasses.replace(f, seq=0) for f in ring.snapshot()],
        )
        self.assertIsNone(self.recorder.store_error)

    def test_governed_flow_hash_computed_at_insert(self) -> None:
        self.recorder.record(_governed_wire_payload())
        row = self.recorder.snapshot_dicts()[0]
        self.assertIsInstance(row["side_effect_hash"], str)
        # The persisted hash equals the one recomputed independently from the
        # flow (what GET /proxy/wire used to compute on the fly).
        flow = self.recorder.snapshot()[0]
        self.assertEqual(row["side_effect_hash"], wire_flow_side_effect_hash(flow.to_dict()))

    def test_non_governed_flow_hash_is_none(self) -> None:
        self.recorder.record(_health_wire_payload())
        self.assertIsNone(self.recorder.snapshot_dicts()[0]["side_effect_hash"])

    def test_non_dict_payload_raises_value_error(self) -> None:
        # Same contract as the ring's record: the endpoint turns this into 422.
        with self.assertRaises(ValueError):
            self.recorder.record("not-a-dict")  # type: ignore[arg-type]

    def test_broken_store_returns_unpersisted_flow_and_recovers(self) -> None:
        real_conn = self.store._conn
        self.store._conn = _BrokenConn()
        with self.assertLogs("recette.proxy.store", level="ERROR"):
            flow = self.recorder.record(_governed_wire_payload())  # must not raise
        # seq=0 marks the flow as normalized but unpersisted (fail-safe).
        self.assertIsInstance(flow, WireFlow)
        self.assertEqual(flow.seq, 0)
        self.assertEqual(self.recorder.store_error, "db down")
        # Recovery: the next SUCCESSFUL insert clears store_error.
        self.store._conn = real_conn
        recovered = self.recorder.record(_governed_wire_payload())
        self.assertGreater(recovered.seq, 0)
        self.assertIsNone(self.recorder.store_error)
        self.assertEqual(len(self.recorder.snapshot()), 1)

    def test_clear_empties_wire_flows_but_not_traces(self) -> None:
        traces = SqliteTraceRecorder(self.store)
        traces.record(_event(), ExecutionResult(ok=True, status_code=200))
        self.recorder.record(_governed_wire_payload())
        self.recorder.clear()
        self.assertEqual(self.recorder.snapshot(), [])
        self.assertEqual(self.recorder.snapshot_dicts(), [])
        # The trace buffer is untouched: clear() deletes wire_flows only.
        self.assertEqual(len(traces.snapshot()), 1)

    def test_wire_and_trace_seq_counters_are_independent(self) -> None:
        traces = SqliteTraceRecorder(self.store)
        traces.record(_event("evt-0001"), ExecutionResult(ok=True, status_code=200))
        traces.record(_event("evt-0002"), ExecutionResult(ok=True, status_code=200))
        flow = self.recorder.record(_governed_wire_payload())
        self.assertEqual(flow.seq, 1)

    def test_snapshot_dicts_preserves_run_id_ok_and_duration(self) -> None:
        self.recorder.record(_governed_wire_payload(run_id="run-x"))
        self.recorder.record(_health_wire_payload())
        self.recorder.record({**_health_wire_payload(), "duration_ms": 12.5, "status_code": 503})
        rows = self.recorder.snapshot_dicts()
        self.assertEqual([r["run_id"] for r in rows], ["run-x", None, None])
        self.assertEqual([r["ok"] for r in rows], [True, True, False])
        for row in rows:
            self.assertIsInstance(row["ok"], bool)
        self.assertEqual([r["duration_ms"] for r in rows], [None, None, 12.5])


class SqliteProxyStoreTests(unittest.TestCase):
    def test_creates_both_tables(self) -> None:
        store = SqliteProxyStore(":memory:")
        names = {
            row[0]
            for row in store._conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        self.assertIn("proxy_traces", names)
        self.assertIn("wire_flows", names)

    def test_file_path_parent_dir_is_created(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "nested" / "dir" / "traces.db"
            store = SqliteProxyStore(str(db_path))
            recorder = SqliteTraceRecorder(store)
            recorder.record(_event(), ExecutionResult(ok=True, status_code=200))
            self.assertEqual(len(recorder.snapshot()), 1)
            self.assertTrue(db_path.exists())
            store.close()

    def test_max_rows_is_stored_at_construction(self) -> None:
        # Retention arrives in Task 3; the ceiling is only carried for now.
        store = SqliteProxyStore(":memory:", max_rows=7)
        self.assertEqual(store.max_rows, 7)


class EnvHelperTests(unittest.TestCase):
    def _with_env(self, key: str, value: str | None) -> None:
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value

    def test_db_path_default_and_override(self) -> None:
        saved = os.environ.get(DB_PATH_ENV)
        try:
            self._with_env(DB_PATH_ENV, None)
            self.assertEqual(db_path_from_env(), DEFAULT_DB_PATH)
            self._with_env(DB_PATH_ENV, "/tmp/custom/proxy.db")
            self.assertEqual(db_path_from_env(), "/tmp/custom/proxy.db")
        finally:
            self._with_env(DB_PATH_ENV, saved)

    def test_max_rows_default_override_and_garbage(self) -> None:
        saved = os.environ.get(MAX_ROWS_ENV)
        try:
            self._with_env(MAX_ROWS_ENV, None)
            self.assertEqual(max_rows_from_env(), DEFAULT_MAX_ROWS)
            self._with_env(MAX_ROWS_ENV, "123")
            self.assertEqual(max_rows_from_env(), 123)
            self._with_env(MAX_ROWS_ENV, "not-a-number")
            self.assertEqual(max_rows_from_env(), DEFAULT_MAX_ROWS)
            self._with_env(MAX_ROWS_ENV, "")
            self.assertEqual(max_rows_from_env(), DEFAULT_MAX_ROWS)
        finally:
            self._with_env(MAX_ROWS_ENV, saved)


if __name__ == "__main__":
    unittest.main()
