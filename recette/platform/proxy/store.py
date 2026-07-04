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

Retention: ``max_rows`` caps each table with an amortized prune -- after a
committed insert whose rowid hits the ``prune_every`` modulo, rows with
``seq <= lastrowid - max_rows`` are deleted. This trims only the DEBUG buffer,
never the audit log (I1). A prune failure never breaks the insert (it already
committed) and never sets ``store_error``.

Queries are parametrized ONLY: the WHERE clause is assembled from a fixed set
of ``column op ?`` fragments joined by AND, with every user value in the params
tuple. LIKE needles are treated as raw substrings: ``%``/``_``/``\\`` are
escaped and the clause carries ``ESCAPE '\\'``, so a needle containing ``%``
matches literally (deterministic, no accidental wildcard).
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
# Amortized prune cadence: the retention DELETE runs only when the inserted
# rowid hits this modulo (constructor-overridable so tests can use 1).
_PRUNE_EVERY = 64

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

_SELECT_TRACES_BASE = (
    "SELECT seq, event_id, timestamp, agent_id, target_system, target, action_type, "
    "resource, request_payload, ok, status_code, side_effect_hash, error, run_id, "
    "response FROM proxy_traces"
)

_SELECT_TRACES = _SELECT_TRACES_BASE + " ORDER BY seq"

_INSERT_WIRE = (
    "INSERT INTO wire_flows (method, scheme, host, port, path, status_code, ok, "
    "content_type, request_body, response_body, run_id, duration_ms, side_effect_hash) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)

_SELECT_WIRE_BASE = (
    "SELECT seq, method, scheme, host, port, path, status_code, ok, content_type, "
    "request_body, response_body, run_id, duration_ms, side_effect_hash "
    "FROM wire_flows"
)

_SELECT_WIRE = _SELECT_WIRE_BASE + " ORDER BY seq"

_COUNT_TRACES = "SELECT COUNT(*) FROM proxy_traces"
_COUNT_WIRE = "SELECT COUNT(*) FROM wire_flows"
_MAX_SEQ_TRACES = "SELECT MAX(seq) FROM proxy_traces"
_MAX_SEQ_WIRE = "SELECT MAX(seq) FROM wire_flows"
_PRUNE_TRACES = "DELETE FROM proxy_traces WHERE seq <= ?"
_PRUNE_WIRE = "DELETE FROM wire_flows WHERE seq <= ?"

# Fixed q fragments: the needle is bound N times via params, never inlined.
# ESCAPE '\' pairs with _like_pattern which escapes \, % and _ in the needle.
_TRACE_Q_FRAGMENT = (
    "(action_type LIKE ? ESCAPE '\\' OR resource LIKE ? ESCAPE '\\' "
    "OR request_payload LIKE ? ESCAPE '\\' OR response LIKE ? ESCAPE '\\')"
)
_TRACE_Q_PARAMS = 4
_WIRE_Q_FRAGMENT = (
    "(path LIKE ? ESCAPE '\\' OR request_body LIKE ? ESCAPE '\\' "
    "OR response_body LIKE ? ESCAPE '\\')"
)
_WIRE_Q_PARAMS = 3


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


def _like_pattern(needle: str) -> str:
    """Substring LIKE pattern with the user needle taken LITERALLY.

    Backslash, ``%`` and ``_`` in the needle are escaped (pairing with the
    ``ESCAPE '\\'`` clause in the fixed fragments), so a needle containing a
    wildcard character matches it as a plain character -- deterministic, never
    an accidental table-wide match.
    """
    escaped = needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return "%" + escaped + "%"


def _compose(base: str, fragments: list[str]) -> str:
    """Append a WHERE clause built ONLY from the fixed ``column op ?``
    fragments above, AND-joined. User values never enter the SQL text --
    they travel in the params tuple (parametrized queries only)."""
    if not fragments:
        return base
    return base + " WHERE " + " AND ".join(fragments)


def _trace_from_row(row: tuple) -> ProxyTrace:
    """Rebuild a ``ProxyTrace`` from a ``_SELECT_TRACES_BASE`` row."""
    return ProxyTrace(
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


class SqliteProxyStore:
    """Owns the SQLite connection, the schema, and a lock for thread safety.

    ``:memory:`` is supported for tests; for a file path the parent directory
    is created. ``max_rows`` caps each table via the amortized prune;
    ``prune_every`` is the modulo cadence (default ``_PRUNE_EVERY``,
    overridable so tests can prune on every insert).
    """

    def __init__(
        self,
        path: str | None = None,
        *,
        max_rows: int | None = None,
        prune_every: int = _PRUNE_EVERY,
    ) -> None:
        self._path = path if path is not None else db_path_from_env()
        self._max_rows = max_rows if max_rows is not None else max_rows_from_env()
        self._prune_every = prune_every
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
        """Retention ceiling per table; ``<= 0`` disables the prune."""
        return self._max_rows

    def _prune(self, delete_sql: str, last_id: int) -> None:
        """Delete rows older than the retention window (called under the lock).

        ``delete_sql`` is one of the fixed ``_PRUNE_*`` statements; the cutoff
        is a bound parameter. Overridable in tests to simulate a prune failure.
        """
        self._conn.execute(delete_sql, (last_id - self._max_rows,))
        self._conn.commit()

    def _maybe_prune(self, delete_sql: str, last_id: int) -> None:
        """Amortized retention, called under the lock AFTER a committed insert.

        Runs only when ``max_rows`` is positive and the fresh rowid hits the
        ``prune_every`` modulo. A prune failure is logged and swallowed and
        does NOT set ``store_error``: the insert already committed, so the
        record path succeeded -- retention is best-effort housekeeping on the
        DEBUG buffer, never a reason to fail or flag the observability path.
        """
        if self._max_rows <= 0 or last_id <= 0 or last_id % self._prune_every != 0:
            return
        try:
            self._prune(delete_sql, last_id)
        except Exception as exc:  # noqa: BLE001 - prune is best-effort by contract
            _LOG.error("proxy store prune failed: %s", exc)

    def insert_trace(self, trace: ProxyTrace) -> None:
        """Insert one trace row. ``seq`` is assigned by SQLite (the passed
        ``trace.seq`` is ignored -- the store owns the monotone order).

        Error lifecycle (owned here, under the lock): a failure records the
        message in ``store_error`` and re-raises; a subsequent successful
        insert clears it back to ``None``. The error never latches forever.
        """
        with self._lock:
            try:
                cursor = self._conn.execute(
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
            self._maybe_prune(_PRUNE_TRACES, cursor.lastrowid or 0)

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
            seq = cursor.lastrowid or 0
            self._maybe_prune(_PRUNE_WIRE, seq)
            return seq

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
        return [_trace_from_row(row) for row in rows]

    def _run_query(
        self,
        select_base: str,
        count_base: str,
        max_base: str,
        fragments: list[str],
        params: list[object],
        since_seq: int | None,
        limit: int | None,
        tail: int | None,
    ) -> tuple[list[tuple], int, int]:
        """Shared query executor: (rows, last_seq, total) in ONE lock scope.

        - ``last_seq`` is MAX(seq) over the WHOLE table (0 when empty) -- the
          delta cursor, deliberately unfiltered.
        - ``total`` counts the FILTERED set, ignoring ``since_seq``/``limit``/
          ``tail`` (the "how many match the filters" number).
        - ``tail`` is the compat "last N of the filtered set": it ignores
          ``since_seq`` and wins over ``limit`` when both are given; rows come
          back ascending (fetched DESC then reversed -- deterministic).
        - ``limit`` returns the first N of the ascending delta.
        """
        with self._lock:
            last_seq = self._conn.execute(max_base).fetchone()[0] or 0
            total = self._conn.execute(_compose(count_base, fragments), tuple(params)).fetchone()[0]
            if tail is not None:
                sql = _compose(select_base, fragments) + " ORDER BY seq DESC LIMIT ?"
                rows = self._conn.execute(sql, (*params, tail)).fetchall()
                rows.reverse()
                return rows, last_seq, total
            item_fragments = list(fragments)
            item_params = list(params)
            if since_seq is not None:
                item_fragments.append("seq > ?")
                item_params.append(since_seq)
            sql = _compose(select_base, item_fragments) + " ORDER BY seq"
            if limit is not None:
                sql = sql + " LIMIT ?"
                item_params.append(limit)
            rows = self._conn.execute(sql, tuple(item_params)).fetchall()
            return rows, last_seq, total

    def query_traces(
        self,
        *,
        since_seq: int | None = None,
        run_id: str | None = None,
        agent_id: str | None = None,
        target: str | None = None,
        outcome: str | None = None,
        q: str | None = None,
        limit: int | None = None,
        tail: int | None = None,
    ) -> tuple[list[tuple], int, int]:
        """Filtered trace rows as (rows, last_seq, total) -- see ``_run_query``.

        ``outcome`` maps "ok" -> ok=1, "fail" -> ok=0; any other value is
        ignored (no filter). ``q`` is a literal substring over action_type,
        resource, request_payload and response (escaped LIKE).
        """
        fragments: list[str] = []
        params: list[object] = []
        if run_id is not None:
            fragments.append("run_id = ?")
            params.append(run_id)
        if agent_id is not None:
            fragments.append("agent_id = ?")
            params.append(agent_id)
        if target is not None:
            fragments.append("target = ?")
            params.append(target)
        if outcome in ("ok", "fail"):
            fragments.append("ok = ?")
            params.append(1 if outcome == "ok" else 0)
        if q is not None:
            fragments.append(_TRACE_Q_FRAGMENT)
            params.extend([_like_pattern(q)] * _TRACE_Q_PARAMS)
        return self._run_query(
            _SELECT_TRACES_BASE,
            _COUNT_TRACES,
            _MAX_SEQ_TRACES,
            fragments,
            params,
            since_seq,
            limit,
            tail,
        )

    def query_wire(
        self,
        *,
        since_seq: int | None = None,
        run_id: str | None = None,
        host: str | None = None,
        method: str | None = None,
        status: int | None = None,
        q: str | None = None,
        limit: int | None = None,
        tail: int | None = None,
    ) -> tuple[list[tuple], int, int]:
        """Filtered wire rows as (rows, last_seq, total) -- see ``_run_query``.

        ``method`` is compared uppercased (the column is stored uppercased by
        ``normalize_flow``); ``status`` is an exact status_code match. ``q`` is
        a literal substring over path, request_body and response_body.
        """
        fragments: list[str] = []
        params: list[object] = []
        if run_id is not None:
            fragments.append("run_id = ?")
            params.append(run_id)
        if host is not None:
            fragments.append("host = ?")
            params.append(host)
        if method is not None:
            fragments.append("method = ?")
            params.append(method.upper())
        if status is not None:
            fragments.append("status_code = ?")
            params.append(status)
        if q is not None:
            fragments.append(_WIRE_Q_FRAGMENT)
            params.extend([_like_pattern(q)] * _WIRE_Q_PARAMS)
        return self._run_query(
            _SELECT_WIRE_BASE,
            _COUNT_WIRE,
            _MAX_SEQ_WIRE,
            fragments,
            params,
            since_seq,
            limit,
            tail,
        )

    def count_traces(self) -> int:
        """COUNT(*) over the trace buffer."""
        with self._lock:
            return int(self._conn.execute(_COUNT_TRACES).fetchone()[0])

    def count_wire(self) -> int:
        """COUNT(*) over the wire buffer."""
        with self._lock:
            return int(self._conn.execute(_COUNT_WIRE).fetchone()[0])

    def last_seq_traces(self) -> int:
        """MAX(seq) over the trace buffer, 0 when empty (the delta cursor)."""
        with self._lock:
            return int(self._conn.execute(_MAX_SEQ_TRACES).fetchone()[0] or 0)

    def last_seq_wire(self) -> int:
        """MAX(seq) over the wire buffer, 0 when empty (the delta cursor)."""
        with self._lock:
            return int(self._conn.execute(_MAX_SEQ_WIRE).fetchone()[0] or 0)

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

    Field mapping keeps the historical recorder contract (same fallbacks:
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

    def query(
        self,
        since_seq: int | None = None,
        run_id: str | None = None,
        agent_id: str | None = None,
        target: str | None = None,
        outcome: str | None = None,
        q: str | None = None,
        limit: int | None = None,
        tail: int | None = None,
    ) -> tuple[list[ProxyTrace], int, int]:
        """Filtered traces as ``(items, last_seq, total)``.

        ``last_seq`` is the unfiltered table MAX(seq) (the delta cursor);
        ``total`` counts the filtered set ignoring ``since_seq``/``limit``/
        ``tail``. ``limit`` and ``tail`` are mutually exclusive in practice;
        when both are given ``tail`` wins (compat: the last N of the filtered
        set, without since_seq semantics). See ``SqliteProxyStore.query_traces``.
        """
        rows, last_seq, total = self._store.query_traces(
            since_seq=since_seq,
            run_id=run_id,
            agent_id=agent_id,
            target=target,
            outcome=outcome,
            q=q,
            limit=limit,
            tail=tail,
        )
        return [_trace_from_row(row) for row in rows], last_seq, total

    def count(self) -> int:
        """Number of buffered traces."""
        return self._store.count_traces()

    def last_seq(self) -> int:
        """Unfiltered MAX(seq) of the trace buffer, 0 when empty."""
        return self._store.last_seq_traces()

    def clear(self) -> None:
        """Empty the debug buffer only (I1-safe: the audit log is untouched)."""
        self._store.clear_traces()


class SqliteWireRecorder:
    """Wire-flow facade over ``SqliteProxyStore`` (mirrors ``SqliteTraceRecorder``).

    Normalization is the shared ``normalize_flow`` from wire.py (one normalizer
    for every ingest path); the governed-action ``side_effect_hash`` is computed
    ONCE at insert (``wire_flow_side_effect_hash``) and persisted, instead of
    being recomputed on every GET /proxy/wire.

    Failure contract of ``record``: a non-dict payload raises ``ValueError``
    (the endpoint turns it into 422 -- the historical recorder contract). A
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

    @classmethod
    def _dict_from_row(cls, row: tuple) -> dict:
        """GET /proxy/wire row shape: the flow dict plus the persisted hash."""
        blob = cls._flow_from_row(row).to_dict()
        blob["side_effect_hash"] = row[13]
        return blob

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
        return [self._dict_from_row(row) for row in self._store.snapshot_wire_rows()]

    def query(
        self,
        since_seq: int | None = None,
        run_id: str | None = None,
        host: str | None = None,
        method: str | None = None,
        status: int | None = None,
        q: str | None = None,
        limit: int | None = None,
        tail: int | None = None,
    ) -> tuple[list[dict], int, int]:
        """Filtered flows as ``(items, last_seq, total)``; items are dicts in
        the ``snapshot_dicts`` shape (side_effect_hash included).

        Same semantics as ``SqliteTraceRecorder.query``: ``last_seq`` is the
        unfiltered table MAX(seq), ``total`` counts the filtered set ignoring
        ``since_seq``/``limit``/``tail``, and ``tail`` wins over ``limit``
        (compat: the last N of the filtered set, without since_seq semantics).
        """
        rows, last_seq, total = self._store.query_wire(
            since_seq=since_seq,
            run_id=run_id,
            host=host,
            method=method,
            status=status,
            q=q,
            limit=limit,
            tail=tail,
        )
        return [self._dict_from_row(row) for row in rows], last_seq, total

    def count(self) -> int:
        """Number of buffered wire flows."""
        return self._store.count_wire()

    def last_seq(self) -> int:
        """Unfiltered MAX(seq) of the wire buffer, 0 when empty."""
        return self._store.last_seq_wire()

    def clear(self) -> None:
        """Empty the debug wire buffer only (I1-safe: the audit log is untouched)."""
        self._store.clear_wire()
