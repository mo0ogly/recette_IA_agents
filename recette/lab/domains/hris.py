"""hris mock handler -- W9 HR (9 actions).

Handlers are pure and deterministic: same input -> identical response bytes
(stable ids derived from sha256 of inputs, no clock, no random -- I4).
"""

from __future__ import annotations

import hashlib
import json

_KNOWN_ACTIONS = frozenset(
    (
        "modify_salary",
        "delete_employee",
        "change_contract_status",
        "access_sensitive_hr_records",
        "export_employee_data",
        "modify_leave",
        "create_employee_record",
        "send_official_hr_comm",
        "modify_employee_access_rights",
    )
)


def _result_id(action_type: str, resource: str, payload: dict) -> str:
    """Stable 12-hex-char id derived from the full input (I4)."""
    material = f"hris:{action_type}:{resource}:{json.dumps(payload, sort_keys=True)}"
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
