"""A1: Audit Plane read endpoints -- event log query + hash-chain verification.

Read-only by construction: the router exposes no write path on the store (I1).
"""

from __future__ import annotations

import json
from collections.abc import Iterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from ...platform.eventstore.protocol import StoredEvent

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/events")
def list_events(
    request: Request,
    from_seq: int = 0,
    agent_id: str | None = None,
    target_system: str | None = None,
    kind: str | None = None,
    event_id: str | None = None,
    limit: int | None = None,
) -> dict:
    store = request.app.state.event_store
    if event_id is not None:
        # event_id is the envelope id of a single stored event (the value
        # carried by verdict evidence links). Resolve it directly, then apply
        # the remaining filters so it composes sanely with kind/agent_id/etc.
        # Stays read-only on the append-only store (I1).
        event = store.get_by_event_id(event_id)
        if event is None or not _matches(
            event, from_seq=from_seq, agent_id=agent_id, target_system=target_system, kind=kind
        ):
            return {"events": []}
        return {"events": [event.to_dict()]}
    events = store.read_from(
        from_seq, limit=limit, agent_id=agent_id, target_system=target_system, kind=kind
    )
    return {"events": [e.to_dict() for e in events]}


def _matches(
    event: StoredEvent,
    *,
    from_seq: int,
    agent_id: str | None,
    target_system: str | None,
    kind: str | None,
) -> bool:
    """Apply the read_from filters to a single resolved event (event_id path).

    Mirrors the store's read_from semantics: seq lower bound, exact kind, and
    payload-scoped agent_id / target_system matching.
    """
    if event.seq < from_seq:
        return False
    if kind is not None and event.kind != kind:
        return False
    payload = event.payload
    if agent_id is not None and payload.get("agent_id") != agent_id:
        return False
    if target_system is not None and payload.get("target_system") != target_system:
        return False
    return True


@router.get("/export.jsonl")
def export_jsonl(request: Request) -> StreamingResponse:
    """Stream the full event log as NDJSON for external tools (SIEM, forensics).

    Read-only on the append-only store (I1): one JSON object per line, ordered
    by seq, keys sorted for byte-stable output (I4-friendly diffing).
    """
    events = request.app.state.event_store.read_from(0)

    def lines() -> Iterator[str]:
        for event in events:
            yield json.dumps(event.to_dict(), sort_keys=True) + "\n"

    return StreamingResponse(lines(), media_type="application/x-ndjson")


@router.get("/verify")
def verify_chain(request: Request) -> dict:
    return request.app.state.event_store.verify_chain().to_dict()
