"""product_cms mock handler -- W11 Product / content (9 actions).

Handlers are pure and deterministic: same input -> identical response bytes
(stable ids derived from sha256 of inputs, no clock, no random -- I4).
"""

from __future__ import annotations

import hashlib
import json

_KNOWN_ACTIONS = frozenset(
    (
        "publish_production",
        "modify_public_page",
        "send_marketing_campaign",
        "modify_pricing",
        "delete_content",
        "change_product_config",
        "enable_feature_all_customers",
        "disable_critical_feature",
        "modify_user_onboarding",
    )
)


def _result_id(action_type: str, resource: str, payload: dict) -> str:
    """Stable 12-hex-char id derived from the full input (I4)."""
    material = f"product_cms:{action_type}:{resource}:{json.dumps(payload, sort_keys=True)}"
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
