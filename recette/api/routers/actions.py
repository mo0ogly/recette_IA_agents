"""A1: governed action execution endpoints -- the API face of the Gateway (I2).

POST /actions/execute is the documented I4 capture point: the wall clock is
read exactly once here at the boundary and recorded into the ActionRequest;
the decision path downstream never reads the host clock.
"""

from __future__ import annotations

import datetime as _dt
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response

from ...platform.approvals.service import ApprovalService
from ...platform.events import ApprovalState, EventKind
from ...platform.gateway import ActionRequest

router = APIRouter(prefix="/actions", tags=["actions"])

_REQUIRED_FIELDS = ("agent_id", "action_type", "target_system", "resource")
_log = logging.getLogger("agentrail.api.actions")


def _bind_identity(request: Request, agent_id: str) -> None:
    """I3: an authenticated agent may only act as itself. A token whose bound
    agent_id differs from the requested one is refused (403, audited). When auth
    is disabled (no principal) there is no identity to bind against -- unchanged."""
    principal = getattr(request.state, "principal", None)
    if principal is not None and principal.kind == "agent" and agent_id != principal.agent_id:
        _log.warning(
            "identity mismatch path=/actions/execute sub=%s bound_agent=%s requested_agent=%s",
            principal.sub,
            principal.agent_id,
            agent_id,
        )
        raise HTTPException(
            status_code=403, detail="agent_id does not match the authenticated identity"
        )


def _capture_timestamp() -> str:
    """I4 capture point: ISO-8601 UTC with Z suffix, captured at the boundary."""
    return _dt.datetime.now(_dt.UTC).isoformat().replace("+00:00", "Z")


@router.post("/execute")
def execute_action(request: Request, body: dict[str, Any], response: Response) -> dict:
    missing = [f for f in _REQUIRED_FIELDS if not body.get(f)]
    if missing:
        raise HTTPException(status_code=400, detail=f"missing required fields: {missing}")
    payload = body.get("payload", {})
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="'payload' must be an object when present")
    _bind_identity(request, str(body["agent_id"]))
    action = ActionRequest(
        agent_id=str(body["agent_id"]),
        action_type=str(body["action_type"]),
        target_system=str(body["target_system"]),
        resource=str(body["resource"]),
        payload=payload,
        timestamp=_capture_timestamp(),
    )
    outcome = request.app.state.gateway.submit(action)
    if outcome.approval_state == ApprovalState.PENDING:
        response.status_code = 202
    return outcome.to_dict()


@router.get("/{event_id}")
def get_action(request: Request, event_id: str) -> dict:
    store = request.app.state.event_store
    stored = store.get_by_event_id(event_id)
    if stored is None:
        raise HTTPException(status_code=404, detail=f"no event {event_id!r}")
    out = stored.to_dict()
    if stored.kind == EventKind.ACTION_REQUESTED:
        # None while still pending; final approval_state once resolved (I6).
        out["resolution"] = ApprovalService(store).resolved_ids().get(event_id)
    return out
