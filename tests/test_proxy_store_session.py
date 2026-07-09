"""Wire store: session_id/instance_id round-trip, cross-session filter, migration.

Phase 6 of the instance-isolation + multi-session tracking plan: the debug wire
buffer now carries WHICH session and WHICH autonomous instance emitted a flow, so
the console can follow one instance across the sessions it acted in. Legacy DBs
(created before the columns) migrate additively, like the earlier ``layers`` column.
"""

from __future__ import annotations

import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from recette.platform.proxy.store import SqliteProxyStore, SqliteWireRecorder


def _payload(session_id: str, instance_id: str, path: str = "/v1/x") -> dict:
    return {
        "method": "post",
        "scheme": "https",
        "host": "api.example.com",
        "port": 443,
        "path": path,
        "status_code": 200,
        "content_type": "application/json",
        "request_body": "{}",
        "response_body": "{}",
        "session_id": session_id,
        "instance_id": instance_id,
    }


class TestWireSessionPersistence(unittest.TestCase):
    def setUp(self) -> None:
        self.store = SqliteProxyStore(":memory:")
        self.rec = SqliteWireRecorder(self.store)

    def tearDown(self) -> None:
        self.store.close()

    def test_round_trip_carries_session_and_instance(self) -> None:
        self.rec.record(_payload("s1", "attacker"))
        flow = self.rec.snapshot()[0]
        self.assertEqual(flow.session_id, "s1")
        self.assertEqual(flow.instance_id, "attacker")
        # And in the dict view the console consumes.
        self.assertEqual(self.rec.snapshot_dicts()[0]["instance_id"], "attacker")

    def test_filter_one_instance_across_sessions(self) -> None:
        self.rec.record(_payload("s1", "attacker"))
        self.rec.record(_payload("s2", "attacker"))
        self.rec.record(_payload("s2", "auditor"))
        # Follow 'attacker' across every session it acted in.
        items, _, total = self.rec.query(instance_id="attacker")
        self.assertEqual(total, 2)
        self.assertEqual({i["session_id"] for i in items}, {"s1", "s2"})
        # Narrow to one session + instance.
        items2, _, total2 = self.rec.query(session_id="s2", instance_id="auditor")
        self.assertEqual(total2, 1)
        self.assertEqual(items2[0]["session_id"], "s2")

    def test_legacy_row_has_null_ids(self) -> None:
        # A flow recorded without the tracking pair stays valid (nullable columns).
        self.rec.record({**_payload("", ""), "session_id": None, "instance_id": None})
        flow = self.rec.snapshot()[0]
        self.assertIsNone(flow.session_id)
        self.assertIsNone(flow.instance_id)

    def test_migration_adds_columns_to_legacy_db(self) -> None:
        # mkdtemp + rmtree(ignore_errors) dodges the Windows WAL WinError 32 the
        # store's own __del__ documents (a freshly-closed handle can linger).
        d = tempfile.mkdtemp()
        try:
            db = str(Path(d) / "legacy.db")
            # Build a pre-migration wire_flows WITHOUT session_id/instance_id/layers.
            conn = sqlite3.connect(db)
            conn.execute(
                "CREATE TABLE wire_flows (seq INTEGER PRIMARY KEY AUTOINCREMENT, "
                "method TEXT NOT NULL, scheme TEXT NOT NULL, host TEXT NOT NULL, "
                "port INTEGER NOT NULL, path TEXT NOT NULL, status_code INTEGER NOT NULL, "
                "ok INTEGER NOT NULL, content_type TEXT NOT NULL, request_body TEXT NOT NULL, "
                "response_body TEXT NOT NULL, run_id TEXT, duration_ms REAL, side_effect_hash TEXT)"
            )
            conn.commit()
            conn.close()
            # Opening the store migrates it; a new insert with the pair round-trips.
            store = SqliteProxyStore(db)
            try:
                rec = SqliteWireRecorder(store)
                rec.record(_payload("s9", "worker"))
                self.assertEqual(rec.snapshot()[0].instance_id, "worker")
                items, _, total = rec.query(session_id="s9")
                self.assertEqual(total, 1)
            finally:
                store.close()
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
