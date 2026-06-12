"""In-memory event store for unit tests. Same chain semantics as SQLite."""

from __future__ import annotations

import threading

from .hashchain import GENESIS_HASH, chain_hash
from .protocol import ChainReport, StoredEvent


class InMemoryEventStore:
    def __init__(self) -> None:
        self._events: list[StoredEvent] = []
        self._lock = threading.Lock()

    def append(
        self, *, event_id: str, kind: str, payload: dict, schema_version: str
    ) -> StoredEvent:
        with self._lock:
            if any(e.event_id == event_id for e in self._events):
                raise ValueError(f"duplicate event_id {event_id!r}")
            prev_hash = self._events[-1].hash if self._events else GENESIS_HASH
            event = StoredEvent(
                seq=len(self._events) + 1,
                event_id=event_id,
                schema_version=schema_version,
                kind=kind,
                payload=payload,
                prev_hash=prev_hash,
                hash=chain_hash(prev_hash, payload),
            )
            self._events.append(event)
            return event

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
        out = []
        for e in self._events:
            if e.seq < seq:
                continue
            if kind is not None and e.kind != kind:
                continue
            if agent_id is not None and e.payload.get("agent_id") != agent_id:
                continue
            if target_system is not None and e.payload.get("target_system") != target_system:
                continue
            out.append(e)
            if limit is not None and len(out) >= limit:
                break
        if tail is not None:
            # Last n of the filtered set, still ascending (live-tail backfill).
            return out[-tail:] if tail > 0 else []
        return out

    def get_by_event_id(self, event_id: str) -> StoredEvent | None:
        return next((e for e in self._events if e.event_id == event_id), None)

    def verify_chain(self) -> ChainReport:
        expected_prev = GENESIS_HASH
        for e in self._events:
            if e.prev_hash != expected_prev or chain_hash(e.prev_hash, e.payload) != e.hash:
                return ChainReport(
                    ok=False,
                    checked=len(self._events),
                    first_break_seq=e.seq,
                    detail="chain break",
                )
            expected_prev = e.hash
        return ChainReport(ok=True, checked=len(self._events))
