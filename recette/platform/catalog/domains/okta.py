"""okta domain action specs -- W1 Identity / Access (14 actions).

Source of truth: docs/tracking/PLAN_high-risk-action-catalog_2026-06-12.md, section W1.
Criticality (Annex C) is the AgentRail default posture, independent from the
implemented verdict; see catalog/model.py::Criticality.
Verdict mapping convention:
- ESC and DENY/ESC rows: privileged role escalates, any other role is denied
  (deny-by-default), privileged_roles = ("identity_admin",).
- DENY rows: denied for every role, privileged_roles = ().
"""

from __future__ import annotations

from ...events import PolicyVerdict
from ..model import ActionSpec, Criticality, RiskLevel

TARGET_SYSTEM = "okta"

_IDENTITY_ADMIN = ("identity_admin",)


def _escalate(
    action_type: str, criticality: Criticality, risk_level: RiskLevel, description: str
) -> ActionSpec:
    """ESC / DENY-ESC row: escalate for identity_admin, deny for everyone else."""
    return ActionSpec(
        target_system=TARGET_SYSTEM,
        action_type=action_type,
        risk_level=risk_level,
        criticality=criticality,
        verdict_privileged=PolicyVerdict.ESCALATE,
        verdict_default=PolicyVerdict.DENY,
        privileged_roles=_IDENTITY_ADMIN,
        description=description,
    )


def _deny(
    action_type: str, criticality: Criticality, risk_level: RiskLevel, description: str
) -> ActionSpec:
    """Pure DENY row: denied for every role, no privileged escape hatch."""
    return ActionSpec(
        target_system=TARGET_SYSTEM,
        action_type=action_type,
        risk_level=risk_level,
        criticality=criticality,
        verdict_privileged=PolicyVerdict.DENY,
        verdict_default=PolicyVerdict.DENY,
        privileged_roles=(),
        description=description,
    )


def _allow(
    action_type: str, criticality: Criticality, risk_level: RiskLevel, description: str
) -> ActionSpec:
    """Routine authorized read row: allow for identity_admin, deny for everyone else."""
    return ActionSpec(
        target_system=TARGET_SYSTEM,
        action_type=action_type,
        risk_level=risk_level,
        criticality=criticality,
        verdict_privileged=PolicyVerdict.ALLOW,
        verdict_default=PolicyVerdict.DENY,
        privileged_roles=_IDENTITY_ADMIN,
        description=description,
    )


ACTIONS: tuple[ActionSpec, ...] = (
    _allow(
        "read_user_profile",
        Criticality.C4,
        RiskLevel.LOW,
        "Read a user's profile attributes (read-only, no mutation).",
    ),
    _escalate("suspend_user", Criticality.C3, RiskLevel.HIGH, "Suspend an Okta user account."),
    _escalate(
        "delete_user",
        Criticality.C1,
        RiskLevel.CRITICAL,
        "Permanently delete an Okta user account.",
    ),
    _escalate(
        "reset_password", Criticality.C3, RiskLevel.HIGH, "Reset the password of an Okta user."
    ),
    _escalate(
        "modify_user_roles", Criticality.C2, RiskLevel.HIGH, "Change the roles assigned to a user."
    ),
    _escalate(
        "add_user_to_admin_group",
        Criticality.C2,
        RiskLevel.CRITICAL,
        "Add a user to an administrative group.",
    ),
    _escalate(
        "create_api_key",
        Criticality.C3,
        RiskLevel.HIGH,
        "Create a new API key for programmatic access.",
    ),
    _escalate("revoke_api_key", Criticality.C3, RiskLevel.MEDIUM, "Revoke an existing API key."),
    _escalate(
        "generate_long_lived_token",
        Criticality.C2,
        RiskLevel.CRITICAL,
        "Generate a long-lived authentication token.",
    ),
    _escalate(
        "modify_mfa_policy",
        Criticality.C1,
        RiskLevel.CRITICAL,
        "Modify the multi-factor authentication policy.",
    ),
    _deny(
        "disable_sso",
        Criticality.C1,
        RiskLevel.CRITICAL,
        "Disable single sign-on for the organization.",
    ),
    _escalate("add_oauth_app", Criticality.C2, RiskLevel.HIGH, "Register a new OAuth application."),
    _escalate(
        "modify_oauth_scopes",
        Criticality.C2,
        RiskLevel.HIGH,
        "Modify the scopes granted to an OAuth application.",
    ),
    _escalate(
        "invite_external_user",
        Criticality.C3,
        RiskLevel.HIGH,
        "Invite an external user into the organization.",
    ),
)
