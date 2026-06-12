"""finance mock handler -- W4 Finance / payments (12 actions).

Handlers are pure and deterministic: same input -> identical response bytes
(stable ids derived from sha256 of inputs, no clock, no random -- I4).
"""

from __future__ import annotations

import hashlib
import json

_KNOWN_ACTIONS = frozenset(
    (
        "trigger_refund",
        "create_payment",
        "modify_iban",
        "add_payee",
        "validate_invoice",
        "modify_supplier_bank_details",
        "create_credit_note",
        "modify_price",
        "apply_mass_discount",
        "export_financial_data",
        "launch_wire_transfer",
        "modify_billing_rule",
    )
)


def _result_id(action_type: str, resource: str, payload: dict) -> str:
    """Stable 12-hex-char id derived from the full input (I4)."""
    material = f"finance:{action_type}:{resource}:{json.dumps(payload, sort_keys=True)}"
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
