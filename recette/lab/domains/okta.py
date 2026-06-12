"""okta mock handler -- W1 Identity / Access (13 actions).

Handlers are pure and deterministic: same input -> identical response bytes
(stable ids derived from sha256 of inputs, no clock, no random -- I4).
"""

from __future__ import annotations

import hashlib
import json

# Action-specific deterministic fields merged into the simulated response.
# Values are constants: same input always produces the same output (I4).
_ACTION_FIELDS: dict[str, dict[str, str]] = {
    "suspend_user": {"user_status": "SUSPENDED"},
    "delete_user": {"user_status": "DEPROVISIONED"},
    "reset_password": {"credential": "password_reset_link_issued"},
    "modify_user_roles": {"roles_state": "updated"},
    "add_user_to_admin_group": {"group_membership": "admin_group_added"},
    "create_api_key": {"key_state": "created"},
    "revoke_api_key": {"key_state": "revoked"},
    "generate_long_lived_token": {"token_state": "issued_long_lived"},
    "modify_mfa_policy": {"mfa_policy_state": "updated"},
    "disable_sso": {"sso_state": "disabled"},
    "add_oauth_app": {"oauth_app_state": "registered"},
    "modify_oauth_scopes": {"oauth_scopes_state": "updated"},
    "invite_external_user": {"invitation_state": "sent"},
}


def handle(action_type: str, resource: str, payload: dict) -> dict | None:
    """Return a deterministic response dict, or None when action is unknown."""
    extra = _ACTION_FIELDS.get(action_type)
    if extra is None:
        return None
    material = f"okta:{action_type}:{resource}:{json.dumps(payload, sort_keys=True)}"
    result_id = hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]
    response: dict = {
        "action": action_type,
        "resource": resource,
        "status": "simulated",
        "result_id": result_id,
    }
    response.update(extra)
    return response
