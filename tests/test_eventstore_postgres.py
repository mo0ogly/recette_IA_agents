"""PostgreSQL event store (Phase 2): same contract as SQLite, plus the multi-writer
guarantee that justifies moving off SQLite -- verified against a REAL Postgres.

Runs only when INSPECT_IA_AGENTS_TEST_POSTGRES_DSN points at a reachable database (skipped
otherwise, e.g. CI without Postgres). The implementation was verified once against a
real Postgres 16; the skip keeps the default suite dependency-free.
"""

from __future__ import annotations

import os
import threading
import unittest

_DSN = os.environ.get("INSPECT_IA_AGENTS_TEST_POSTGRES_DSN")

try:
    import psycopg  # noqa: F401

    from recette.platform.eventstore.postgres_store import PostgresEventStore

    _HAS_PG = True
except ImportError:  # pragma: no cover - psycopg is the optional [postgres] extra
    _HAS_PG = False

from recette.platform.eventstore.hashchain import GENESIS_HASH, chain_hash  # noqa: E402


@unittest.skipUnless(_HAS_PG and _DSN, "requires psycopg + INSPECT_IA_AGENTS_TEST_POSTGRES_DSN")
class TestPostgresEventStore(unittest.TestCase):
    def setUp(self) -> None:
        # Fresh schema per test: triggers block DELETE/TRUNCATE (I1), so reset is a
        # DDL DROP (the only legitimate way to wipe an immutable log -- a test fixture,
        # never a runtime path).
        with psycopg.connect(_DSN, autocommit=True) as conn:
            conn.execute("DROP TABLE IF EXISTS events CASCADE")
            conn.execute("DROP FUNCTION IF EXISTS events_immutable() CASCADE")
        self.store = PostgresEventStore(_DSN)
        self.addCleanup(self.store.close)

    def _append(self, eid: str, payload: dict, kind: str = "action_denied") -> object:
        return self.store.append(event_id=eid, kind=kind, payload=payload, schema_version="2.0")

    def test_seq_is_monotone_and_chain_links(self) -> None:
        e1 = self._append("EV1", {"n": 1})
        e2 = self._append("EV2", {"n": 2}, kind="action_executed")
        self.assertEqual((e1.seq, e2.seq), (1, 2))
        self.assertEqual(e1.prev_hash, GENESIS_HASH)
        self.assertEqual(e2.prev_hash, e1.hash)
        self.assertEqual(e2.hash, chain_hash(e1.hash, {"n": 2}))

    def test_verify_chain_ok(self) -> None:
        for i in range(5):
            self._append(f"EV{i}", {"n": i})
        report = self.store.verify_chain()
        self.assertTrue(report.ok)
        self.assertEqual(report.checked, 5)

    def test_verify_chain_detects_tamper(self) -> None:
        for i in range(3):
            self._append(f"EV{i}", {"n": i})
        # An attacker with DB rights drops the trigger and mutates a row; the hash
        # chain must still expose the break.
        with psycopg.connect(_DSN, autocommit=True) as conn:
            conn.execute("DROP TRIGGER events_no_update ON events")
            conn.execute("UPDATE events SET payload = '{\"n\":99}'::jsonb WHERE seq = 2")
        report = self.store.verify_chain()
        self.assertFalse(report.ok)
        self.assertEqual(report.first_break_seq, 2)

    def test_filters_and_lookup(self) -> None:
        self._append("EV1", {"agent_id": "a1", "target_system": "okta"})
        self._append("EV2", {"agent_id": "a2", "target_system": "cloud"}, kind="action_executed")
        self.assertEqual(len(self.store.read_from(agent_id="a1")), 1)
        self.assertEqual(len(self.store.read_from(target_system="cloud")), 1)
        self.assertEqual(len(self.store.read_from(kind="action_executed")), 1)
        self.assertEqual(len(self.store.read_from(limit=1)), 1)
        self.assertIsNotNone(self.store.get_by_event_id("EV2"))
        self.assertIsNone(self.store.get_by_event_id("missing"))

    def test_tail_returns_last_n_ascending(self) -> None:
        for i in range(10):
            self._append(f"EV{i}", {"n": i}, "action_executed" if i % 2 == 0 else "action_denied")
        self.assertEqual([e.seq for e in self.store.read_from(tail=5)], [6, 7, 8, 9, 10])
        denied = self.store.read_from(tail=2, kind="action_denied")
        self.assertEqual([e.payload["n"] for e in denied], [7, 9])
        self.assertEqual(len(self.store.read_from(tail=100)), 10)
        self.assertEqual(self.store.read_from(tail=0), [])

    def test_limit_and_tail_mutually_exclusive(self) -> None:
        self._append("EV1", {})
        with self.assertRaises(ValueError):
            self.store.read_from(limit=1, tail=1)

    def test_duplicate_event_id_rejected(self) -> None:
        self._append("EV1", {})
        with self.assertRaises(psycopg.errors.UniqueViolation):
            self._append("EV1", {})

    def test_raw_update_and_delete_rejected_by_trigger(self) -> None:
        self._append("EV1", {"agent_id": "a"})
        with psycopg.connect(_DSN, autocommit=True) as conn:
            with self.assertRaises(psycopg.errors.RaiseException) as up:
                conn.execute("UPDATE events SET payload = '{}'::jsonb WHERE seq = 1")
            self.assertIn("immutable", str(up.exception))
        with psycopg.connect(_DSN, autocommit=True) as conn:
            with self.assertRaises(psycopg.errors.RaiseException) as dl:
                conn.execute("DELETE FROM events WHERE seq = 1")
            self.assertIn("immutable", str(dl.exception))

    def test_concurrent_writers_keep_one_valid_chain(self) -> None:
        # Two independent connections (simulating two hosts) append concurrently.
        # The transaction-scoped advisory lock serialises them so the hash chain
        # cannot fork: verify_chain stays OK and every seq/id is unique.
        n = 25
        errors: list[Exception] = []

        def writer(tag: str) -> None:
            store = PostgresEventStore(_DSN)
            try:
                for i in range(n):
                    store.append(
                        event_id=f"{tag}-{i}",
                        kind="action_denied",
                        payload={"w": tag, "i": i},
                        schema_version="2.0",
                    )
            except Exception as exc:  # surfaced to the assertion below
                errors.append(exc)
            finally:
                store.close()

        threads = [threading.Thread(target=writer, args=(t,)) for t in ("A", "B")]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        report = self.store.verify_chain()
        self.assertTrue(report.ok, report.detail)
        self.assertEqual(report.checked, 2 * n)
        all_events = self.store.read_from()
        self.assertEqual(len({e.event_id for e in all_events}), 2 * n)
        self.assertEqual([e.seq for e in all_events], list(range(1, 2 * n + 1)))


if __name__ == "__main__":
    unittest.main()
