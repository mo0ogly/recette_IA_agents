"""SQLite event store -- Phase 1 implementation (event-store-decision.md).

Immutability (I1) is ENFORCED by triggers, not discipline: any UPDATE or
DELETE on the events table aborts. seq is a monotone AUTOINCREMENT primary
key giving a total replay order (I4). Appends are serialized by a process
lock (SQLite is single-writer; FastAPI sync endpoints run in a thread pool).

Failure mode: any storage error raises -- the gateway treats an unaudited
action as not executable (fail-safe).
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from .hashchain import GENESIS_HASH, chain_hash
from .protocol import ChainReport, StoredEvent

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id TEXT NOT NULL UNIQUE,
  schema_version TEXT NOT NULL,
  kind TEXT NOT NULL,
  payload TEXT NOT NULL,
  prev_hash TEXT NOT NULL,
  hash TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
  BEGIN SELECT RAISE(ABORT, 'events are immutable (I1)'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
  BEGIN SELECT RAISE(ABORT, 'events are immutable (I1)'); END;
"""


class SqliteEventStore:
    def __init__(self, path: Path | str) -> None:
        self._path = str(path)
        self._lock = threading.Lock()
        if self._path != ":memory:":
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: access is serialized by self._lock.
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "SqliteEventStore":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def __del__(self) -> None:
        # Release the SQLite connection (and its WAL/SHM handles) when a store is
        # dropped without an explicit close. On POSIX a leaked handle is harmless;
        # on Windows an open handle keeps a lock on the db file, so a dropped
        # store would block deleting its directory (e.g. a test's TemporaryDirectory
        # cleanup -> WinError 32). Guard every failure mode: __del__ must never raise.
        conn = getattr(self, "_conn", None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    # --- EventStore protocol ---

    def append(
        self, *, event_id: str, kind: str, payload: dict, schema_version: str
    ) -> StoredEvent:
        with self._lock:
            row = self._conn.execute("SELECT hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
            prev_hash = row[0] if row is not None else GENESIS_HASH
            digest = chain_hash(prev_hash, payload)
            cur = self._conn.execute(
                "INSERT INTO events (event_id, schema_version, kind, payload, prev_hash, hash)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    event_id,
                    schema_version,
                    kind,
                    json.dumps(payload, sort_keys=True, separators=(",", ":")),
                    prev_hash,
                    digest,
                ),
            )
            self._conn.commit()
            seq = cur.lastrowid
            if seq is None:  # pragma: no cover - sqlite always sets lastrowid on INSERT
                raise RuntimeError("sqlite INSERT returned no rowid")
            return StoredEvent(
                seq=seq,
                event_id=event_id,
                schema_version=schema_version,
                kind=kind,
                payload=payload,
                prev_hash=prev_hash,
                hash=digest,
            )

    def read_from(
        self,
        seq: int = 0,
        *,
        limit: int | None = None,
        tail: int | None = None,
        agent_id: str | None = None,
        target_system: str | None = None,
        kind: str | None = None,
    ) -> list[StoredEvent]:
        if limit is not None and tail is not None:
            raise ValueError("limit and tail are mutually exclusive")
        query = (
            "SELECT seq, event_id, schema_version, kind, payload, prev_hash, hash"
            " FROM events WHERE seq >= ?"
        )
        params: list[object] = [seq]
        if kind is not None:
            query += " AND kind = ?"
            params.append(kind)
        # agent_id / target_system live inside the JSON payload; filter via json_extract.
        if agent_id is not None:
            query += " AND json_extract(payload, '$.agent_id') = ?"
            params.append(agent_id)
        if target_system is not None:
            query += " AND json_extract(payload, '$.target_system') = ?"
            params.append(target_system)
        if tail is not None:
            # Last n of the filtered set, returned ascending: pick them via a
            # DESC LIMIT subquery, then restore the replay order (I4).
            # query is internally built from fixed clauses; all values are ? params
            query = f"SELECT * FROM ({query} ORDER BY seq DESC LIMIT ?) ORDER BY seq ASC"  # noqa: S608  # nosec B608
            params.append(max(tail, 0))
        else:
            query += " ORDER BY seq ASC"
            if limit is not None:
                query += " LIMIT ?"
                params.append(limit)
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_event(r) for r in rows]

    def get_by_event_id(self, event_id: str) -> StoredEvent | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT seq, event_id, schema_version, kind, payload, prev_hash, hash"
                " FROM events WHERE event_id = ?",
                (event_id,),
            ).fetchone()
        return self._row_to_event(row) if row is not None else None

    def verify_chain(self) -> ChainReport:
        with self._lock:
            rows = self._conn.execute(
                "SELECT seq, payload, prev_hash, hash FROM events ORDER BY seq ASC"
            ).fetchall()
        expected_prev = GENESIS_HASH
        for seq, payload_text, prev_hash, digest in rows:
            payload = json.loads(payload_text)
            if prev_hash != expected_prev:
                return ChainReport(
                    ok=False,
                    checked=len(rows),
                    first_break_seq=seq,
                    detail="prev_hash does not match previous event hash",
                )
            if chain_hash(prev_hash, payload) != digest:
                return ChainReport(
                    ok=False,
                    checked=len(rows),
                    first_break_seq=seq,
                    detail="stored hash does not match recomputed hash",
                )
            expected_prev = digest
        return ChainReport(ok=True, checked=len(rows))

    @staticmethod
    def _row_to_event(row: tuple) -> StoredEvent:
        seq, event_id, schema_version, kind, payload_text, prev_hash, digest = row
        return StoredEvent(
            seq=seq,
            event_id=event_id,
            schema_version=schema_version,
            kind=kind,
            payload=json.loads(payload_text),
            prev_hash=prev_hash,
            hash=digest,
        )
