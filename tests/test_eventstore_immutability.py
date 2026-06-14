"""I1: immutability is ENFORCED by SQLite triggers, not discipline."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from recette.platform.eventstore.sqlite_store import SqliteEventStore


class TestEventStoreImmutability(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "events.db"
        self.store = SqliteEventStore(self.path)
        self.store.append(
            event_id="EV1", kind="action_denied", payload={"agent_id": "a"}, schema_version="2.0"
        )

    def tearDown(self) -> None:
        self.store.close()
        self._tmp.cleanup()

    def test_raw_update_is_rejected_by_trigger(self) -> None:
        conn = sqlite3.connect(self.path)
        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            conn.execute("UPDATE events SET payload = '{}' WHERE seq = 1")
        self.assertIn("immutable", str(ctx.exception))
        conn.close()

    def test_raw_delete_is_rejected_by_trigger(self) -> None:
        conn = sqlite3.connect(self.path)
        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            conn.execute("DELETE FROM events WHERE seq = 1")
        self.assertIn("immutable", str(ctx.exception))
        conn.close()


if __name__ == "__main__":
    unittest.main()
