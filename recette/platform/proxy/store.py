"""SQLite-backed store for proxy traces and wire flows (debug observability).

This module is a DEBUG observability buffer for the side-effect proxy path
(I5), NOT the audit event store: it retains recent ``ProxyTrace`` rows (and,
from Task 2 on, mitmproxy wire flows) so the console can query them with
retention and indexes instead of an in-memory ring. Clearing or pruning this
store NEVER touches the audit log -- the durable truth stays in the audit
plane (I1); this buffer is jettable and rebuildable.

Determinism (I4): the store introduces no wall-clock and no randomness.
``timestamp`` is the event's already-captured logical clock (an input carried
by the event), ordering is the monotone SQLite ``seq`` (AUTOINCREMENT, which
keeps its counter across DELETE via ``sqlite_sequence``), and JSON blobs are
serialized canonically (sorted keys, compact separators) so a replayed stream
produces byte-identical rows.

Fail-safe: ``SqliteTraceRecorder.record`` never raises -- a storage failure is
logged and surfaced via ``store_error``, never propagated into the execution
path (failure-modes.md).

Retention/prune arrives in Task 3; ``max_rows`` is accepted and stored at
construction now but not yet enforced.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os
import sqlite3
import threading
from pathlib import Path

from ..events import PlatformActionEvent
from .protocol import ExecutionResult
from .reconcile import wire_flow_side_effect_hash
from .tracing import ProxyTrace
from .wire import WireFlow, normalize_flow

DB_PATH_ENV = "INSPECT_IA_AGENTS_PROXY_DB"
DEFAULT_DB_PATH = ".run/proxy_traces.db"
MAX_ROWS_ENV = "INSPECT_IA_AGENTS_PROXY_DB_MAX_ROWS"
DEFAULT_MAX_ROWS = 50_000

_LOG = logging.getLogger("recette.proxy.store")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS proxy_traces (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id TEXT NOT NULL, timestamp TEXT NOT NULL, agent_id TEXT NOT NULL,
  target_system TEXT NOT NULL, target TEXT NOT NULL, action_type TEXT NOT NULL,
  resource TEXT NOT NULL, request_payload TEXT NOT NULL,
  ok INTEGER NOT NULL, status_code INTEGER NOT NULL,
  side_effect_hash TEXT, error TEXT, run_id TEXT, response TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_traces_run ON proxy_traces(run_id);
CREATE INDEX IF NOT EXISTS idx_traces_agent ON proxy_traces(agent_id);
CREATE TABLE IF NOT EXISTS wire_flows (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  method TEXT NOT NULL, scheme TEXT NOT NULL, host TEXT NOT NULL,
  port INTEGER NOT NULL, path TEXT NOT NULL, status_code INTEGER NOT NULL,
  ok INTEGER NOT NULL, content_type TEXT NOT NULL,
  request_body TEXT NOT NULL, response_body TEXT NOT NULL,
  run_id TEXT, duration_ms REAL, side_effect_hash TEXT
);
CREATE INDEX IF NOT EXISTS idx_wire_run ON wire_flows(run_id);
CREATE INDEX IF NOT EXISTS idx_wire_host ON wire_flows(host);
"""

_INSERT_TRACE = (
    "INSERT INTO proxy_traces (event_id, timestamp, agent_id, target_system, target, "
    "action_type, resource, request_payload, ok, status_code, side_effect_hash, error, "
    "run_id, response) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)

_SELECT_TRACES = (
    "SELECT seq, event_id, timestamp, agent_id, target_system, target, action_type, "
    "resource, request_payload, ok, status_code, side_effect_hash, error, run_id, "
    "response FROM proxy_traces ORDER BY seq"
)

_INSERT_WIRE = (
    "INSERT INTO wire_flows (method, scheme, host, port, path, status_code, ok, "
    "content_type, request_body, response_body, run_id, duration_ms, side_effect_hash) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)

_SELECT_WIRE = (
    "SELECT seq, method, scheme, host, port, path, status_code, ok, content_type, "
    "request_body, response_body, run_id, duration_ms, side_effect_hash "
    "FROM wire_flows ORDER BY seq"
)


def db_path_from_env() -> str:
    """Read the store path from the environment (R5: no hardcoded path)."""
    raw = os.environ.get(DB_PATH_ENV, "").strip()
    return raw or DEFAULT_DB_PATH


def max_rows_from_env() -> int:
    """Read the retention ceiling from the environment (R5).

    Accepts any int-parseable value; garbage or unset falls back to the
    default (fail-safe: a bad env var never breaks the store).
    """
    raw = os.environ.get(MAX_ROWS_ENV, "").strip()
    if not raw:
        return DEFAULT_MAX_ROWS
    try:
        return int(raw)
    except ValueError:
        return DEFAULT_MAX_ROWS


def _dumps(blob: dict) -> str:
    """Canonical JSON serialization: compact and byte-stable (I4)."""
    return json.dumps(blob, sort_keys=True, separators=(",", ":"))


class SqliteProxyStore:
    """Owns the SQLite connection, the schema, and a lock for thread safety.

    ``:memory:`` is supported for tests; for a file path the parent directory
    is created. ``max_rows`` is carried for the Task 3 prune, unused for now.
    """

    def __init__(self, path: str | None = None, *, max_rows: int | None = None) -> None:
        self._path = path if path is not None else db_path_from_env()
        self._max_rows = max_rows if max_rows is not None else max_rows_from_env()
        if self._path != ":memory:":
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._lock = threading.Lock()
        self._store_error: str | None = None
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    @property
    def store_error(self) -> str | None:
        """Last storage failure message, ``None`` when healthy."""
        return self._store_error

    @property
    def max_rows(self) -> int:
        """Retention ceiling carried for the Task 3 prune (unused for now)."""
        return self._max_rows

    def insert_trace(self, trace: ProxyTrace) -> None:
        """Insert one trace row. ``seq`` is assigned by SQLite (the passed
        ``trace.seq`` is ignored -- the store owns the monotone order).

        Error lifecycle (owned here, under the lock): a failure records the
        message in ``store_error`` and re-raises; a subsequent successful
        insert clears it back to ``None``. The error never latches forever.
        """
        with self._lock:
            try:
                self._conn.execute(
                    _INSERT_TRACE,
                    (
                        trace.event_id,
                        trace.timestamp,
                        trace.agent_id,
                        trace.target_system,
                        trace.target,
                        trace.action_type,
                        trace.resource,
                        _dumps(trace.request_payload),
                        int(trace.ok),
                        trace.status_code,
                        trace.side_effect_hash,
                        trace.error,
                        trace.run_id,
                        _dumps(trace.response),
                    ),
                )
                self._conn.commit()
            except Exception as exc:
                self._store_error = str(exc)
                raise
            self._store_error = None

    def insert_wire(self, flow: WireFlow, side_effect_hash: str | None) -> int:
        """Insert one wire-flow row and return the SQLite-assigned ``seq``.

        Same lock + commit + error lifecycle as ``insert_trace``: a failure
        records the message in ``store_error`` and re-raises; a subsequent
        successful insert clears it back to ``None``. The passed ``flow.seq``
        is ignored -- AUTOINCREMENT owns the monotone order (its counter is
        independent from the traces one; each table has its own).
        """
        with self._lock:
            try:
                cursor = self._conn.execute(
                    _INSERT_WIRE,
                    (
                        flow.method,
                        flow.scheme,
                        flow.host,
                        flow.port,
                        flow.path,
                        flow.status_code,
                        int(flow.ok),
                        flow.content_type,
                        flow.request_body,
                        flow.response_body,
                        flow.run_id,
                        flow.duration_ms,
                        side_effect_hash,
                    ),
                )
                self._conn.commit()
            except Exception as exc:
                self._store_error = str(exc)
                raise
            self._store_error = None
            # A successful INSERT always sets lastrowid; `or 0` only narrows
            # the Optional for typing, it is never hit on this path.
            return cursor.lastrowid or 0

    def snapshot_wire_rows(self) -> list[tuple]:
        """All wire rows in monotone ``seq`` order (raw tuples, hash included)."""
        with self._lock:
            return self._conn.execute(_SELECT_WIRE).fetchall()

    def clear_wire(self) -> None:
        """Empty the DEBUG wire buffer only -- traces and audit log untouched."""
        with self._lock:
            self._conn.execute("DELETE FROM wire_flows")
            self._conn.commit()

    def snapshot_traces(self) -> list[ProxyTrace]:
        """All traces in monotone ``seq`` order, rebuilt as ``ProxyTrace``."""
        with self._lock:
            rows = self._conn.execute(_SELECT_TRACES).fetchall()
        return [
            ProxyTrace(
                seq=row[0],
                event_id=row[1],
                timestamp=row[2],
                agent_id=row[3],
                target_system=row[4],
                target=row[5],
                action_type=row[6],
                resource=row[7],
                request_payload=json.loads(row[8]),
                ok=bool(row[9]),
                status_code=row[10],
                side_effect_hash=row[11],
                error=row[12],
                run_id=row[13],
                response=json.loads(row[14]),
            )
            for row in rows
        ]

    def clear_traces(self) -> None:
        """Empty the DEBUG trace buffer only -- never the audit log (I1).

        SQLite AUTOINCREMENT keeps its counter in ``sqlite_sequence`` across
        DELETE, so ``seq`` stays monotone after a clear.
        """
        with self._lock:
            self._conn.execute("DELETE FROM proxy_traces")
            self._conn.commit()

    def close(self) -> None:
        """Close the underlying connection (tests / shutdown hygiene)."""
        with self._lock:
            self._conn.close()


class SqliteTraceRecorder:
    """``TraceRecorder`` facade over ``SqliteProxyStore``.

    Field mapping is identical to ``RingTraceRecorder.record`` (same fallbacks:
    ``target = result.target or event.target_system``). ``record`` NEVER
    raises: observability must never break the I5 execution path.
    """

    def __init__(self, store: SqliteProxyStore) -> None:
        self._store = store

    @property
    def store_error(self) -> str | None:
        """Delegates to the store: last failure message, ``None`` when healthy."""
        return self._store.store_error

    def record(
        self, event: PlatformActionEvent, result: ExecutionResult, run_id: str | None = None
    ) -> None:
        try:
            trace = ProxyTrace(
                seq=0,  # assigned by SQLite AUTOINCREMENT on insert
                event_id=event.event_id,
                timestamp=event.timestamp,
                agent_id=event.agent_id,
                target_system=event.target_system,
                # Fallback to event.target_system (always a non-empty str) keeps
                # ProxyTrace.target a str by construction (see tracing.py).
                target=result.target or event.target_system,
                action_type=event.action_type,
                resource=event.resource,
                request_payload=dict(event.payload),
                ok=result.ok,
                status_code=result.status_code,
                side_effect_hash=result.side_effect_hash,
                error=result.error,
                run_id=run_id,
                response=dict(result.response),
            )
            self._store.insert_trace(trace)
        except Exception as exc:  # noqa: BLE001 - recording must never break execution
            # The store already tracked the failure in store_error (its own
            # lifecycle, under its lock); here we only swallow and log.
            _LOG.error("proxy trace record failed: %s", exc)

    def snapshot(self) -> list[ProxyTrace]:
        return self._store.snapshot_traces()

    def clear(self) -> None:
        """Empty the debug buffer only (I1-safe: the audit log is untouched)."""
        self._store.clear_traces()


class SqliteWireRecorder:
    """Wire-flow facade over ``SqliteProxyStore`` (mirrors ``SqliteTraceRecorder``).

    Normalization is the shared ``normalize_flow`` from wire.py (DRY with the
    in-memory ring); the governed-action ``side_effect_hash`` is computed ONCE
    at insert (``wire_flow_side_effect_hash``) and persisted, instead of being
    recomputed on every GET /proxy/wire.

    Failure contract of ``record``: a non-dict payload raises ``ValueError``
    (the endpoint turns it into 422 -- same contract as the ring's record). A
    STORAGE failure never raises: the normalized flow is returned with
    ``seq=0`` (marking it unpersisted), the failure is logged and surfaced via
    ``store_error`` (fail-safe: observability never breaks the I5 path).
    """

    def __init__(self, store: SqliteProxyStore) -> None:
        self._store = store

    @property
    def store_error(self) -> str | None:
        """Delegates to the store: last failure message, ``None`` when healthy."""
        return self._store.store_error

    def record(self, payload: dict) -> WireFlow:
        # ValueError from a non-dict payload propagates (the 422 contract).
        # seq=0 is a placeholder: AUTOINCREMENT assigns the real seq at insert.
        flow = normalize_flow(payload, 0)
        try:
            effect_hash = wire_flow_side_effect_hash(flow.to_dict())
            seq = self._store.insert_wire(flow, effect_hash)
            return dataclasses.replace(flow, seq=seq)
        except Exception as exc:  # noqa: BLE001 - recording must never break execution
            # The store already tracked the failure in store_error (its own
            # lifecycle, under its lock); here we only swallow and log. The
            # returned flow keeps seq=0: normalized but unpersisted.
            _LOG.error("wire flow record failed: %s", exc)
            return flow

    @staticmethod
    def _flow_from_row(row: tuple) -> WireFlow:
        # Column order matches _SELECT_WIRE; row[13] (side_effect_hash) is not
        # a WireFlow field (wire.py is unchanged) -- see snapshot_dicts.
        return WireFlow(
            seq=row[0],
            method=row[1],
            scheme=row[2],
            host=row[3],
            port=row[4],
            path=row[5],
            status_code=row[6],
            ok=bool(row[7]),
            content_type=row[8],
            request_body=row[9],
            response_body=row[10],
            run_id=row[11],
            duration_ms=row[12],
        )

    def snapshot(self) -> list[WireFlow]:
        """All flows in monotone ``seq`` order, rebuilt as ``WireFlow``."""
        return [self._flow_from_row(row) for row in self._store.snapshot_wire_rows()]

    def snapshot_dicts(self) -> list[dict]:
        """Dict view of the rows WITH the persisted ``side_effect_hash``.

        This is the GET /proxy/wire shape: the hash the endpoint used to
        recompute on the fly is now read straight from the column (NULL ->
        ``None``); ``run_id`` stays ``None`` vs string, ``ok`` is a bool and
        ``duration_ms`` is ``None``-safe via the dataclass rebuild.
        """
        rows = []
        for row in self._store.snapshot_wire_rows():
            blob = self._flow_from_row(row).to_dict()
            blob["side_effect_hash"] = row[13]
            rows.append(blob)
        return rows

    def clear(self) -> None:
        """Empty the debug wire buffer only (I1-safe: the audit log is untouched)."""
        self._store.clear_wire()
