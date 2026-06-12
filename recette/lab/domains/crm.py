"""crm mock handler -- W3 CRM / Sales workstream.

Handlers are pure and deterministic: same input -> identical response bytes
(stable ids derived from sha256 of inputs, no clock, no random -- I4).
The known action set mirrors the W3 catalog (recette/platform/catalog/domains/crm.py)
without importing it: the lab plane stays decoupled from the catalog plane and
the test suite asserts both stay in sync.
"""

from __future__ import annotations

import hashlib
import json

_KNOWN_ACTIONS: frozenset[str] = frozenset(
    {
        "bulk_modify_contacts",
        "delete_contacts",
        "export_customer_base",
        "bulk_modify_deals",
        "change_strategic_account_owner",
        "modify_sales_pipeline",
        "send_mass_email",
        "change_opportunity_amounts",
        "modify_sensitive_fields",
        "sync_crm_to_external",
    }
)


def _result_id(action_type: str, resource: str, payload: dict) -> str:
    """Derive a stable 12-hex-char id from the simulated action inputs (I4)."""
    material = f"crm:{action_type}:{resource}:{json.dumps(payload, sort_keys=True)}"
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
