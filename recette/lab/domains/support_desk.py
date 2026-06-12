"""support_desk mock handler -- W7 Support / customer ops (10 actions).

Handlers are pure and deterministic: same input -> identical response bytes
(stable ids derived from sha256 of inputs, no clock, no random -- I4).
"""

from __future__ import annotations

import hashlib
import json

_KNOWN_ACTIONS = frozenset(
    (
        "bulk_close_tickets",
        "modify_critical_ticket_status",
        "send_auto_customer_reply",
        "grant_goodwill_credit",
        "delete_ticket",
        "export_customer_conversations",
        "modify_sla",
        "reassign_ticket_volume",
        "access_vip_tickets",
        "share_support_data_external",
    )
)


def _result_id(action_type: str, resource: str, payload: dict) -> str:
    """Stable 12-hex-char id derived from the full input (I4)."""
    material = f"support_desk:{action_type}:{resource}:{json.dumps(payload, sort_keys=True)}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]


def handle(action_type: str, resource: str, payload: dict) -> dict | None:
    """Return a deterministic response dict, or None when action is unknown."""
    if action_type not in _KNOWN_ACTIONS:
        return None
    return {
        "action": action_type,
        "resource": resource,
        "status": "simulated",
        "result_id": _result_id(action_type, resource, payload),
    }
