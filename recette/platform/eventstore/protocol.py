"""EventStore Protocol -- defined before any implementation (event-store-decision.md)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class StoredEvent:
    seq: int
    event_id: str
    schema_version: str
    kind: str
    payload: dict
    prev_hash: str
    hash: str

    def to_dict(self) -> dict:
        return {
            "seq": self.seq,
            "event_id": self.event_id,
            "schema_version": self.schema_version,
            "kind": self.kind,
            "payload": self.payload,
            "prev_hash": self.prev_hash,
            "hash": self.hash,
        }


@dataclass(frozen=True)
class ChainReport:
    ok: bool
    checked: int
    first_break_seq: int | None = None
    detail: str | None = None

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "checked": self.checked,
            "first_break_seq": self.first_break_seq,
            "detail": self.detail,
        }


@runtime_checkable
class EventStore(Protocol):
    """Append-only audit log (I1). Implementations never expose UPDATE/DELETE."""

    def append(
        self, *, event_id: str, kind: str, payload: dict, schema_version: str
    ) -> StoredEvent:
        """Append one event, computing the prev_hash chain. Raises on failure."""
        ...

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
        """Read filtered events ordered by seq ascending.

        ``limit`` keeps the FIRST n of the filtered set; ``tail`` keeps the
        LAST n (still returned ascending -- backfill for live tails). The two
        are mutually exclusive: passing both raises ValueError.
        """
        ...

    def get_by_event_id(self, event_id: str) -> StoredEvent | None: ...

    def verify_chain(self) -> ChainReport:
        """Recompute every hash from genesis; report the first break if any."""
        ...
