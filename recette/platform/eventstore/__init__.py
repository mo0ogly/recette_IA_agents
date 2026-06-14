"""Audit Plane event store (Phase 1 SQLite, per event-store-decision.md).

The store is append-only (I1) with a sha256 hash chain; replay order is the
monotonic seq (I4). Failure mode: a store error never lets an action execute
unaudited -- callers treat append failure as a hard stop.
"""

import os

from .memory_store import InMemoryEventStore
from .protocol import ChainReport, EventStore, StoredEvent
from .sqlite_store import SqliteEventStore

__all__ = [
    "ChainReport",
    "EventStore",
    "InMemoryEventStore",
    "SqliteEventStore",
    "StoredEvent",
    "build_event_store_from_env",
]

DEFAULT_SQLITE_PATH = "data/inspect_ia_agents.events.db"


class EventStoreConfigError(RuntimeError):
    """The configured event-store backend is unknown or missing required config."""


def build_event_store_from_env() -> EventStore:
    """Construct the event store selected by INSPECT_IA_AGENTS_EVENT_STORE (Phase 1/2 switch).

    sqlite (default) -> file at INSPECT_IA_AGENTS_EVENT_STORE_PATH.
    postgres         -> PostgresEventStore at INSPECT_IA_AGENTS_DATABASE_URL (R8). psycopg is
                        imported lazily so the Postgres dependency stays optional
                        (extra [postgres]); the SQLite path never needs it.
    """
    backend = os.environ.get("INSPECT_IA_AGENTS_EVENT_STORE", "sqlite").strip().lower()
    if backend == "sqlite":
        path = os.environ.get("INSPECT_IA_AGENTS_EVENT_STORE_PATH", DEFAULT_SQLITE_PATH)
        return SqliteEventStore(path)
    if backend == "postgres":
        dsn = os.environ.get("INSPECT_IA_AGENTS_DATABASE_URL")
        if not dsn:
            raise EventStoreConfigError(
                "INSPECT_IA_AGENTS_EVENT_STORE=postgres requires INSPECT_IA_AGENTS_DATABASE_URL"
            )
        try:
            from .postgres_store import PostgresEventStore
        except ImportError as exc:  # psycopg not installed
            raise EventStoreConfigError(
                "postgres backend needs the [postgres] extra (psycopg)"
            ) from exc
        return PostgresEventStore(dsn)
    raise EventStoreConfigError(f"unknown INSPECT_IA_AGENTS_EVENT_STORE backend: {backend!r}")
