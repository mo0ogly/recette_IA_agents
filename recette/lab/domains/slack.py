"""slack mock handler (workstream W6, Phase 1).

Handlers are pure and deterministic: same input -> identical response bytes
(stable ids derived from sha256 of inputs, no clock, no random -- I4).
"""

from __future__ import annotations

import hashlib
import json

# Action types mirrored from the W6 slack catalog
# (recette/platform/catalog/domains/slack.py). Kept as an immutable constant
# so the handler stays pure; the test suite asserts catalog/handler sync.
_KNOWN_ACTIONS: frozenset[str] = frozenset(
    {
        "send_message_external_channel",
        "invite_external_user",
        "share_sensitive_file",
        "create_public_channel",
        "modify_workspace_permissions",
        "delete_channel",
        "publish_company_announcement",
        "send_message_as_executive",
        "access_confidential_channel",
        "export_slack_history",
    }
)


def _result_id(action_type: str, resource: str, payload: dict) -> str:
    material = f"slack:{action_type}:{resource}:{json.dumps(payload, sort_keys=True)}"
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
        "target_system": "slack",
    }
