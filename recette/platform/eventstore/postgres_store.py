"""PostgreSQL event store -- Phase 2 implementation (event-store-decision.md).

Same contract as SqliteEventStore, behind the same EventStore protocol, for the
moment the Audit Plane outgrows a single host: a file-backed SQLite log cannot be
shared over the network nor written by several hosts at once. This store can.

Parity with Phase 1, with the Postgres-specific guarantees Phase 2 needs:
- ``seq BIGSERIAL`` primary key -> a monotone total replay order (I4);
- immutability (I1) ENFORCED by triggers (a plpgsql RAISE on UPDATE/DELETE),
  not discipline, exactly like the SQLite triggers;
- a sha256 hash chain (``prev_hash``) over the canonical payload (I1 integrity),
  byte-identical to the SQLite store because ``chain_hash`` canonicalises;
- appends serialised by a transaction-scoped advisory lock
  (``pg_advisory_xact_lock``): this is what makes the chain correct under
  CONCURRENT writers across processes/hosts -- the real reason to move off SQLite.

Failure mode: any storage error raises -- the gateway treats an unaudited action
as not executable (fail-safe). Credentials come from the DSN (env/secret store,
R8), never hardcoded.
"""

from __future__ import annotations

import threading

import psycopg
from psycopg.types.json import Jsonb

from .hashchain import GENESIS_HASH, chain_hash
from .protocol import ChainReport, StoredEvent

# A fixed key for the transaction-scoped advisory lock that serialises appends
# across every connection/host writing to this log ("AREV" = AgentRail EVents).
_APPEND_LOCK_KEY = 0x41524556
# A separate key serialising the idempotent schema setup: concurrent CREATE OR
# REPLACE FUNCTION / CREATE TRIGGER on the system catalogs otherwise race with
# "tuple concurrently updated" when two stores are constructed at the same time.
_SCHEMA_LOCK_KEY = 0x41524553

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  seq BIGSERIAL PRIMARY KEY,
  event_id TEXT NOT NULL UNIQUE,
  schema_version TEXT NOT NULL,
  kind TEXT NOT NULL,
  payload JSONB NOT NULL,
  prev_hash TEXT NOT NULL,
  hash TEXT NOT NULL
);
CREATE OR REPLACE FUNCTION events_immutable() RETURNS trigger AS $$
BEGIN RAISE EXCEPTION 'events are immutable (I1)'; END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS events_no_update ON events;
CREATE TRIGGER events_no_update BEFORE UPDATE ON events
  FOR EACH ROW EXECUTE FUNCTION events_immutable();
DROP TRIGGER IF EXISTS events_no_delete ON events;
CREATE TRIGGER events_no_delete BEFORE DELETE ON events
  FOR EACH ROW EXECUTE FUNCTION events_immutable();
"""


class PostgresEventStore:
    """Append-only audit log on PostgreSQL (I1). Never exposes UPDATE/DELETE."""

    def __init__(self, dsn: str) -> None:
        self._lock = threading.Lock()
        # autocommit for DDL + explicit per-append transactions for the chain.
        self._conn = psycopg.connect(dsn, autocommit=True)
        # Serialise the idempotent schema setup across concurrent store inits: a
        # transaction-scoped advisory lock makes the DDL safe under multi-writer.
        with self._conn.transaction():
            self._conn.execute("SELECT pg_advisory_xact_lock(%s)", (_SCHEMA_LOCK_KEY,))
            self._conn.execute(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    # --- EventStore protocol ---

    def append(
        self, *, event_id: str, kind: str, payload: dict, schema_version: str
    ) -> StoredEvent:
        # In-process serialisation (self._lock) plus a cross-process advisory lock
        # held for the transaction: two writers anywhere cannot fork the chain.
        with self._lock, self._conn.transaction():
            self._conn.execute("SELECT pg_advisory_xact_lock(%s)", (_APPEND_LOCK_KEY,))
            row = self._conn.execute("SELECT hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
            prev_hash = row[0] if row is not None else GENESIS_HASH
            digest = chain_hash(prev_hash, payload)
            inserted = self._conn.execute(
                "INSERT INTO events (event_id, schema_version, kind, payload, prev_hash, hash)"
                " VALUES (%s, %s, %s, %s, %s, %s) RETURNING seq",
                (event_id, schema_version, kind, Jsonb(payload), prev_hash, digest),
            ).fetchone()
        if inserted is None:  # pragma: no cover - RETURNING always yields a row
            raise RuntimeError("postgres INSERT returned no seq")
        return StoredEvent(
            seq=inserted[0],
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
            " FROM events WHERE seq >= %s"
        )
        params: list[object] = [seq]
        if kind is not None:
            query += " AND kind = %s"
            params.append(kind)
        # agent_id / target_system live inside the JSONB payload.
        if agent_id is not None:
            query += " AND payload->>'agent_id' = %s"
            params.append(agent_id)
        if target_system is not None:
            query += " AND payload->>'target_system' = %s"
            params.append(target_system)
        if tail is not None:
            # Last n of the filtered set, returned ascending (I4 replay order).
            # nosec B608: `query` is composed only of static literal fragments; every
            # caller value is bound via a %s placeholder in `params`, never interpolated.
            query = f"SELECT * FROM ({query} ORDER BY seq DESC LIMIT %s) sub ORDER BY seq ASC"  # nosec B608
            params.append(max(tail, 0))
        else:
            query += " ORDER BY seq ASC"
            if limit is not None:
                query += " LIMIT %s"
                params.append(limit)
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_event(r) for r in rows]

    def get_by_event_id(self, event_id: str) -> StoredEvent | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT seq, event_id, schema_version, kind, payload, prev_hash, hash"
                " FROM events WHERE event_id = %s",
                (event_id,),
            ).fetchone()
        return self._row_to_event(row) if row is not None else None

    def verify_chain(self) -> ChainReport:
        with self._lock:
            rows = self._conn.execute(
                "SELECT seq, payload, prev_hash, hash FROM events ORDER BY seq ASC"
            ).fetchall()
        expected_prev = GENESIS_HASH
        for seq, payload, prev_hash, digest in rows:
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
        seq, event_id, schema_version, kind, payload, prev_hash, digest = row
        return StoredEvent(
            seq=seq,
            event_id=event_id,
            schema_version=schema_version,
            kind=kind,
            payload=payload,  # JSONB -> dict via psycopg
            prev_hash=prev_hash,
            hash=digest,
        )
