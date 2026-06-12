"""SQLite event store: seq monotone, hash chain, filters, tamper detection."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from recette.platform.eventstore.hashchain import GENESIS_HASH, chain_hash
from recette.platform.eventstore.sqlite_store import SqliteEventStore


class TestSqliteEventStore(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "events.db"
        self.store = SqliteEventStore(self.path)

    def tearDown(self) -> None:
        self.store.close()
        self._tmp.cleanup()

    def test_seq_is_monotone_and_chain_links(self) -> None:
        e1 = self.store.append(
            event_id="EV1", kind="action_denied", payload={"n": 1}, schema_version="2.0"
        )
        e2 = self.store.append(
            event_id="EV2", kind="action_executed", payload={"n": 2}, schema_version="2.0"
        )
        self.assertEqual(e1.seq, 1)
        self.assertEqual(e2.seq, 2)
        self.assertEqual(e1.prev_hash, GENESIS_HASH)
        self.assertEqual(e2.prev_hash, e1.hash)
        self.assertEqual(e2.hash, chain_hash(e1.hash, {"n": 2}))

    def test_verify_chain_ok(self) -> None:
        for i in range(5):
            self.store.append(
                event_id=f"EV{i}", kind="action_denied", payload={"n": i}, schema_version="2.0"
            )
        report = self.store.verify_chain()
        self.assertTrue(report.ok)
        self.assertEqual(report.checked, 5)

    def test_verify_chain_detects_tamper_on_copy(self) -> None:
        for i in range(3):
            self.store.append(
                event_id=f"EV{i}", kind="action_denied", payload={"n": i}, schema_version="2.0"
            )
        self.store.close()
        # Tamper a COPY out-of-band: drop triggers first (an attacker with file
        # access can do that) -- verify_chain must still catch the mutation.
        conn = sqlite3.connect(self.path)
        conn.execute("DROP TRIGGER events_no_update")
        conn.execute("UPDATE events SET payload = '{\"n\":99}' WHERE seq = 2")
        conn.commit()
        conn.close()
        store = SqliteEventStore(self.path)
        report = store.verify_chain()
        store.close()
        self.assertFalse(report.ok)
        self.assertEqual(report.first_break_seq, 2)

    def test_filters(self) -> None:
        self.store.append(
            event_id="EV1",
            kind="action_denied",
            payload={"agent_id": "a1", "target_system": "okta"},
            schema_version="2.0",
        )
        self.store.append(
            event_id="EV2",
            kind="action_executed",
            payload={"agent_id": "a2", "target_system": "cloud"},
            schema_version="2.0",
        )
        self.assertEqual(len(self.store.read_from(agent_id="a1")), 1)
        self.assertEqual(len(self.store.read_from(target_system="cloud")), 1)
        self.assertEqual(len(self.store.read_from(kind="action_executed")), 1)
        self.assertEqual(len(self.store.read_from(limit=1)), 1)
        self.assertIsNotNone(self.store.get_by_event_id("EV2"))
        self.assertIsNone(self.store.get_by_event_id("missing"))

    def test_tail_returns_last_n_ascending(self) -> None:
        for i in range(10):
            self.store.append(
                event_id=f"EV{i}",
                kind="action_executed" if i % 2 == 0 else "action_denied",
                payload={"n": i},
                schema_version="2.0",
            )
        # Last 5 of the whole log, still ascending by seq (I4 replay order).
        tail = self.store.read_from(tail=5)
        self.assertEqual([e.seq for e in tail], [6, 7, 8, 9, 10])
        # tail composes with filters: last 2 of the filtered set.
        denied = self.store.read_from(tail=2, kind="action_denied")
        self.assertEqual([e.payload["n"] for e in denied], [7, 9])
        # tail larger than the log returns everything.
        self.assertEqual(len(self.store.read_from(tail=100)), 10)
        # tail=0 returns nothing.
        self.assertEqual(self.store.read_from(tail=0), [])

    def test_limit_and_tail_are_mutually_exclusive(self) -> None:
        self.store.append(event_id="EV1", kind="action_denied", payload={}, schema_version="2.0")
        with self.assertRaises(ValueError):
            self.store.read_from(limit=1, tail=1)

    def test_duplicate_event_id_rejected(self) -> None:
        self.store.append(event_id="EV1", kind="action_denied", payload={}, schema_version="2.0")
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.append(
                event_id="EV1", kind="action_denied", payload={}, schema_version="2.0"
            )


if __name__ == "__main__":
    unittest.main()
