"""crm domain action specs -- W3 CRM / Sales workstream.

Source of truth: section "### W3" of
docs/tracking/PLAN_high-risk-action-catalog_2026-06-12.md.

Every W3 row is ESC or DENY/ESC, so the whole domain shares one verdict
mapping: a privileged sales_admin role escalates (approval required, I6),
any other role is denied (deny-by-default).
"""

from __future__ import annotations

from ...events import PolicyVerdict
from ..model import ActionSpec, RiskLevel

TARGET_SYSTEM = "crm"

_PRIVILEGED_ROLES: tuple[str, ...] = ("sales_admin",)


def _spec(action_type: str, risk_level: RiskLevel, description: str) -> ActionSpec:
    """Build a crm ActionSpec with the shared ESC/DENY verdict mapping."""
    return ActionSpec(
        target_system=TARGET_SYSTEM,
        action_type=action_type,
        risk_level=risk_level,
        verdict_privileged=PolicyVerdict.ESCALATE,
        verdict_default=PolicyVerdict.DENY,
        privileged_roles=_PRIVILEGED_ROLES,
        description=description,
    )


def _allow(action_type: str, risk_level: RiskLevel, description: str) -> ActionSpec:
    """Routine authorized read row: allow for sales_admin, deny for everyone else."""
    return ActionSpec(
        target_system=TARGET_SYSTEM,
        action_type=action_type,
        risk_level=risk_level,
        verdict_privileged=PolicyVerdict.ALLOW,
        verdict_default=PolicyVerdict.DENY,
        privileged_roles=_PRIVILEGED_ROLES,
        description=description,
    )


ACTIONS: tuple[ActionSpec, ...] = (
    _allow(
        "read_contact_record",
        RiskLevel.LOW,
        "Read a single contact record (read-only, no bulk, no export).",
    ),
    _spec(
        "bulk_modify_contacts",
        RiskLevel.HIGH,
        "Modify a large batch of CRM contacts in one operation.",
    ),
    _spec(
        "delete_contacts",
        RiskLevel.HIGH,
        "Delete contact records from the CRM.",
    ),
    _spec(
        "export_customer_base",
        RiskLevel.CRITICAL,
        "Export the full customer base out of the CRM.",
    ),
    _spec(
        "bulk_modify_deals",
        RiskLevel.HIGH,
        "Modify a large batch of deals in one operation.",
    ),
    _spec(
        "change_strategic_account_owner",
        RiskLevel.HIGH,
        "Change the owner of a strategic account.",
    ),
    _spec(
        "modify_sales_pipeline",
        RiskLevel.MEDIUM,
        "Modify the structure or stages of the sales pipeline.",
    ),
    _spec(
        "send_mass_email",
        RiskLevel.HIGH,
        "Send a mass email to CRM contacts.",
    ),
    _spec(
        "change_opportunity_amounts",
        RiskLevel.HIGH,
        "Change the monetary amounts of sales opportunities.",
    ),
    _spec(
        "modify_sensitive_fields",
        RiskLevel.MEDIUM,
        "Modify sensitive fields on CRM records.",
    ),
    _spec(
        "sync_crm_to_external",
        RiskLevel.HIGH,
        "Synchronize CRM data to an external system.",
    ),
)
