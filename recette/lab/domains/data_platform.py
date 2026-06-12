"""data_platform mock handler -- W5 Data / confidentiality (11 actions).

Handlers are pure and deterministic: same input -> identical response bytes
(stable ids derived from sha256 of inputs, no clock, no random -- I4).
"""

from __future__ import annotations

import hashlib
import json

# Action-specific deterministic fields merged into the simulated response.
# Values are constants: same input always produces the same output (I4).
_ACTION_FIELDS: dict[str, dict[str, str]] = {
    "export_customer_data": {"export_state": "customer_data_exported"},
    "download_full_database": {"download_state": "full_database_dump_created"},
    "share_pii_file": {"share_state": "pii_file_shared"},
    "send_data_to_external_domain": {"transfer_state": "sent_to_external_domain"},
    "modify_retention_policy": {"retention_policy_state": "updated"},
    "delete_logs": {"logs_state": "deleted"},
    "delete_audit_evidence": {"audit_evidence_state": "deleted"},
    "access_hr_data": {"access_state": "hr_data_accessed"},
    "access_medical_data": {"access_state": "medical_data_accessed"},
    "access_sensitive_financial_data": {"access_state": "financial_data_accessed"},
    "extract_data_to_external_llm": {"extraction_state": "sent_to_external_llm"},
}


def handle(action_type: str, resource: str, payload: dict) -> dict | None:
    """Return a deterministic response dict, or None when action is unknown."""
    extra = _ACTION_FIELDS.get(action_type)
    if extra is None:
        return None
    material = f"data_platform:{action_type}:{resource}:{json.dumps(payload, sort_keys=True)}"
    result_id = hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]
    response: dict = {
        "action": action_type,
        "resource": resource,
        "status": "simulated",
        "result_id": result_id,
    }
    response.update(extra)
    return response
