"""okta domain action specs -- W1 Identity / Access (13 actions).

Source of truth: docs/tracking/PLAN_high-risk-action-catalog_2026-06-12.md, section W1.
Verdict mapping convention:
- ESC and DENY/ESC rows: privileged role escalates, any other role is denied
  (deny-by-default), privileged_roles = ("identity_admin",).
- DENY rows: denied for every role, privileged_roles = ().
"""

from __future__ import annotations

from ...events import PolicyVerdict
from ..model import ActionSpec, RiskLevel

TARGET_SYSTEM = "okta"

_IDENTITY_ADMIN = ("identity_admin",)


def _escalate(action_type: str, risk_level: RiskLevel, description: str) -> ActionSpec:
    """ESC / DENY-ESC row: escalate for identity_admin, deny for everyone else."""
    return ActionSpec(
        target_system=TARGET_SYSTEM,
        action_type=action_type,
        risk_level=risk_level,
        verdict_privileged=PolicyVerdict.ESCALATE,
        verdict_default=PolicyVerdict.DENY,
        privileged_roles=_IDENTITY_ADMIN,
        description=description,
    )


def _deny(action_type: str, risk_level: RiskLevel, description: str) -> ActionSpec:
    """Pure DENY row: denied for every role, no privileged escape hatch."""
    return ActionSpec(
        target_system=TARGET_SYSTEM,
        action_type=action_type,
        risk_level=risk_level,
        verdict_privileged=PolicyVerdict.DENY,
        verdict_default=PolicyVerdict.DENY,
        privileged_roles=(),
        description=description,
    )


ACTIONS: tuple[ActionSpec, ...] = (
    _escalate("suspend_user", RiskLevel.HIGH, "Suspend an Okta user account."),
    _escalate("delete_user", RiskLevel.CRITICAL, "Permanently delete an Okta user account."),
    _escalate("reset_password", RiskLevel.HIGH, "Reset the password of an Okta user."),
    _escalate("modify_user_roles", RiskLevel.HIGH, "Change the roles assigned to a user."),
    _escalate(
        "add_user_to_admin_group",
        RiskLevel.CRITICAL,
        "Add a user to an administrative group.",
    ),
    _escalate("create_api_key", RiskLevel.HIGH, "Create a new API key for programmatic access."),
    _escalate("revoke_api_key", RiskLevel.MEDIUM, "Revoke an existing API key."),
    _escalate(
        "generate_long_lived_token",
        RiskLevel.CRITICAL,
        "Generate a long-lived authentication token.",
    ),
    _escalate(
        "modify_mfa_policy",
        RiskLevel.CRITICAL,
        "Modify the multi-factor authentication policy.",
    ),
    _deny("disable_sso", RiskLevel.CRITICAL, "Disable single sign-on for the organization."),
    _escalate("add_oauth_app", RiskLevel.HIGH, "Register a new OAuth application."),
    _escalate(
        "modify_oauth_scopes",
        RiskLevel.HIGH,
        "Modify the scopes granted to an OAuth application.",
    ),
    _escalate(
        "invite_external_user",
        RiskLevel.HIGH,
        "Invite an external user into the organization.",
    ),
)
