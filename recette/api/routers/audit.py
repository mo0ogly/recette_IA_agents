"""A1: Audit Plane read endpoints -- event log query + hash-chain verification.

Read-only by construction: the router exposes no write path on the store (I1).
"""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/events")
def list_events(
    request: Request,
    from_seq: int = 0,
    agent_id: str | None = None,
    target_system: str | None = None,
    kind: str | None = None,
    limit: int | None = None,
) -> dict:
    events = request.app.state.event_store.read_from(
        from_seq, limit=limit, agent_id=agent_id, target_system=target_system, kind=kind
    )
    return {"events": [e.to_dict() for e in events]}


@router.get("/verify")
def verify_chain(request: Request) -> dict:
    return request.app.state.event_store.verify_chain().to_dict()
