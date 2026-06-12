"""Audit Plane event store (Phase 1 SQLite, per event-store-decision.md).

The store is append-only (I1) with a sha256 hash chain; replay order is the
monotonic seq (I4). Failure mode: a store error never lets an action execute
unaudited -- callers treat append failure as a hard stop.
"""

from .memory_store import InMemoryEventStore
from .protocol import ChainReport, EventStore, StoredEvent
from .sqlite_store import SqliteEventStore

__all__ = [
    "ChainReport",
    "EventStore",
    "InMemoryEventStore",
    "SqliteEventStore",
    "StoredEvent",
]
