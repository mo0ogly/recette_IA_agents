"""legal_dms mock handler -- W10 Legal / compliance (9 actions).

Handlers are pure and deterministic: same input -> identical response bytes
(stable ids derived from sha256 of inputs, no clock, no random -- I4).
"""

from __future__ import annotations

import hashlib
import json

_KNOWN_ACTIONS = frozenset(
    (
        "generate_or_send_contract",
        "modify_contract_clause",
        "delete_legal_document",
        "share_confidential_document",
        "accept_contract_terms",
        "submit_regulatory_document",
        "modify_internal_policy",
        "delete_evidence_item",
        "export_audit_file",
    )
)


def _result_id(action_type: str, resource: str, payload: dict) -> str:
    """Stable 12-hex-char id derived from the full input (I4)."""
    material = f"legal_dms:{action_type}:{resource}:{json.dumps(payload, sort_keys=True)}"
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
