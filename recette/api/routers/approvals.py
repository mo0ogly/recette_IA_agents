"""A1: approval inbox + resolution endpoints (I6).

The inbox is a fold over the event log (ApprovalService); resolutions are new
events appended through the Gateway, never mutations (I1). The sweep endpoint
is an I4 capture point: when no 'now' is supplied, the wall clock is read once
here and passed down as an input.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ...platform.approvals.service import ApprovalService
from ...platform.approvals.state_machine import ApprovalAction, InvalidTransition
from ...platform.gateway import GatewayError

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.get("")
def list_approvals(request: Request, state: str = "pending") -> dict:
    if state != "pending":
        raise HTTPException(status_code=400, detail="only state=pending is supported")
    service = ApprovalService(request.app.state.event_store)
    return {"pending": [p.to_dict() for p in service.pending()]}


def _resolve(request: Request, event_id: str, body: dict[str, Any], action: ApprovalAction) -> dict:
    approver = body.get("approver")
    if not isinstance(approver, str) or not approver:
        raise HTTPException(status_code=400, detail="body must contain a non-empty 'approver'")
    reason = body.get("reason")
    if reason is not None and not isinstance(reason, str):
        raise HTTPException(status_code=400, detail="'reason' must be a string when present")
    try:
        outcome = request.app.state.gateway.resolve_approval(
            pending_event_id=event_id, action=action, approver=approver, reason=reason
        )
    except GatewayError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return outcome.to_dict()


@router.post("/sweep-timeouts")
def sweep_timeouts(request: Request, body: dict[str, Any] | None = None) -> dict:
    now = (body or {}).get("now")
    if now is None:
        # I4 capture point: clock read once at the boundary, passed as input.
        now = _dt.datetime.now(_dt.UTC).isoformat().replace("+00:00", "Z")
    elif not isinstance(now, str):
        raise HTTPException(status_code=400, detail="'now' must be an ISO-8601 string")
    return {"timed_out": request.app.state.gateway.sweep_timeouts(now_iso=now)}


@router.post("/{event_id}/approve")
def approve(request: Request, event_id: str, body: dict[str, Any]) -> dict:
    return _resolve(request, event_id, body, ApprovalAction.APPROVE)


@router.post("/{event_id}/deny")
def deny(request: Request, event_id: str, body: dict[str, Any]) -> dict:
    return _resolve(request, event_id, body, ApprovalAction.DENY)
