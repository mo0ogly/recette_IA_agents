"""support_desk domain action specs -- W7 Support / customer ops (11 actions).

Source of truth: docs/tracking/PLAN_high-risk-action-catalog_2026-06-12.md, section W7.
Criticality (Annex C) is the AgentRail default posture, independent from the
implemented verdict; see catalog/model.py::Criticality.
Verdict mapping convention:
- ESC and DENY/ESC rows: privileged role escalates, any other role is denied
  (deny-by-default), privileged_roles = ("support_admin",).
- DENY rows: denied for every role, privileged_roles = () (none in W7).
"""

from __future__ import annotations

from ...events import PolicyVerdict
from ..model import ActionSpec, Criticality, RiskLevel

TARGET_SYSTEM = "support_desk"

_SUPPORT_ADMIN = ("support_admin",)


def _escalate(
    action_type: str, criticality: Criticality, risk_level: RiskLevel, description: str
) -> ActionSpec:
    """ESC / DENY-ESC row: escalate for support_admin, deny for everyone else."""
    return ActionSpec(
        target_system=TARGET_SYSTEM,
        action_type=action_type,
        risk_level=risk_level,
        criticality=criticality,
        verdict_privileged=PolicyVerdict.ESCALATE,
        verdict_default=PolicyVerdict.DENY,
        privileged_roles=_SUPPORT_ADMIN,
        description=description,
    )


def _allow(
    action_type: str, criticality: Criticality, risk_level: RiskLevel, description: str
) -> ActionSpec:
    """Routine authorized read row: allow for support_admin, deny for everyone else."""
    return ActionSpec(
        target_system=TARGET_SYSTEM,
        action_type=action_type,
        risk_level=risk_level,
        criticality=criticality,
        verdict_privileged=PolicyVerdict.ALLOW,
        verdict_default=PolicyVerdict.DENY,
        privileged_roles=_SUPPORT_ADMIN,
        description=description,
    )


ACTIONS: tuple[ActionSpec, ...] = (
    _allow(
        "read_ticket",
        Criticality.C4,
        RiskLevel.LOW,
        "Read a standard support ticket (read-only, no VIP, no export).",
    ),
    _escalate(
        "bulk_close_tickets",
        Criticality.C2,
        RiskLevel.MEDIUM,
        "Close a large batch of support tickets at once.",
    ),
    _escalate(
        "modify_critical_ticket_status",
        Criticality.C3,
        RiskLevel.MEDIUM,
        "Change the status of a critical support ticket.",
    ),
    _escalate(
        "send_auto_customer_reply",
        Criticality.C4,
        RiskLevel.MEDIUM,
        "Send an automated reply to a customer.",
    ),
    _escalate(
        "grant_goodwill_credit",
        Criticality.C3,
        RiskLevel.HIGH,
        "Grant a goodwill credit to a customer account.",
    ),
    _escalate(
        "delete_ticket",
        Criticality.C2,
        RiskLevel.HIGH,
        "Permanently delete a support ticket.",
    ),
    _escalate(
        "export_customer_conversations",
        Criticality.C2,
        RiskLevel.CRITICAL,
        "Export customer conversation history out of the system.",
    ),
    _escalate(
        "modify_sla",
        Criticality.C2,
        RiskLevel.HIGH,
        "Modify a service level agreement definition.",
    ),
    _escalate(
        "reassign_ticket_volume",
        Criticality.C3,
        RiskLevel.MEDIUM,
        "Reassign a large volume of tickets to another queue or agent.",
    ),
    _escalate(
        "access_vip_tickets",
        Criticality.C3,
        RiskLevel.HIGH,
        "Access tickets belonging to VIP customers.",
    ),
    _escalate(
        "share_support_data_external",
        Criticality.C2,
        RiskLevel.HIGH,
        "Share support data with an external party.",
    ),
)
