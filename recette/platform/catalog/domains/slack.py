"""slack domain action specs (workstream W6, Phase 1).

Eleven sensitive Slack / communication actions from the high-risk action catalog
plan (docs/tracking/PLAN_high-risk-action-catalog_2026-06-12.md, section W6).
Criticality (Annex C) is the AgentRail default posture, independent from the
implemented verdict; see catalog/model.py::Criticality.
Verdict convention: ESC and DENY/ESC rows escalate for workspace_admin and
deny everyone else (deny-by-default); pure DENY rows deny every role.
"""

from __future__ import annotations

from ...events import PolicyVerdict
from ..model import ActionSpec, Criticality, RiskLevel

TARGET_SYSTEM = "slack"

_ADMIN = ("workspace_admin",)


def _escalate(
    action_type: str, criticality: Criticality, risk_level: RiskLevel, description: str
) -> ActionSpec:
    """ESC / DENY-ESC row: escalate for workspace_admin, deny by default."""
    return ActionSpec(
        target_system=TARGET_SYSTEM,
        action_type=action_type,
        risk_level=risk_level,
        criticality=criticality,
        verdict_privileged=PolicyVerdict.ESCALATE,
        verdict_default=PolicyVerdict.DENY,
        privileged_roles=_ADMIN,
        description=description,
    )


def _deny(
    action_type: str, criticality: Criticality, risk_level: RiskLevel, description: str
) -> ActionSpec:
    """Pure DENY row: denied for every role, no privileged escape."""
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
    """Routine authorized read row: allow for workspace_admin, deny for everyone else."""
    return ActionSpec(
        target_system=TARGET_SYSTEM,
        action_type=action_type,
        risk_level=risk_level,
        criticality=criticality,
        verdict_privileged=PolicyVerdict.ALLOW,
        verdict_default=PolicyVerdict.DENY,
        privileged_roles=_ADMIN,
        description=description,
    )


ACTIONS: tuple[ActionSpec, ...] = (
    _allow(
        "read_public_channel",
        Criticality.C4,
        RiskLevel.LOW,
        "Read messages in a public channel (read-only, no export).",
    ),
    _escalate(
        "send_message_external_channel",
        Criticality.C3,
        RiskLevel.MEDIUM,
        "Send a message to a channel shared with an external organization",
    ),
    _escalate(
        "invite_external_user",
        Criticality.C3,
        RiskLevel.HIGH,
        "Invite a user from outside the workspace as guest or member",
    ),
    _escalate(
        "share_sensitive_file",
        Criticality.C2,
        RiskLevel.HIGH,
        "Share a file classified as sensitive in a Slack conversation",
    ),
    _escalate(
        "create_public_channel",
        Criticality.C3,
        RiskLevel.MEDIUM,
        "Create a new public channel visible to the whole workspace",
    ),
    _escalate(
        "modify_workspace_permissions",
        Criticality.C2,
        RiskLevel.HIGH,
        "Modify workspace-level permission or role settings",
    ),
    _escalate(
        "delete_channel",
        Criticality.C2,
        RiskLevel.MEDIUM,
        "Delete a channel and its message history",
    ),
    _escalate(
        "publish_company_announcement",
        Criticality.C2,
        RiskLevel.HIGH,
        "Publish an announcement to a company-wide broadcast channel",
    ),
    _deny(
        "send_message_as_executive",
        Criticality.C1,
        RiskLevel.CRITICAL,
        "Send a message impersonating an executive identity",
    ),
    _escalate(
        "access_confidential_channel",
        Criticality.C2,
        RiskLevel.HIGH,
        "Access a private channel marked confidential",
    ),
    _escalate(
        "export_slack_history",
        Criticality.C1,
        RiskLevel.CRITICAL,
        "Export workspace message history in bulk",
    ),
)
