"""legal_dms domain action specs -- W10 Legal / compliance (9 actions).

Source of truth: docs/tracking/PLAN_high-risk-action-catalog_2026-06-12.md, section W10.
Verdict mapping convention:
- ESC and DENY/ESC rows: privileged role escalates, any other role is denied
  (deny-by-default), privileged_roles = ("legal_admin",).
- DENY rows (delete_evidence_item): denied for every role, privileged_roles = ().
"""

from __future__ import annotations

from ...events import PolicyVerdict
from ..model import ActionSpec, RiskLevel

TARGET_SYSTEM = "legal_dms"

_LEGAL_ADMIN = ("legal_admin",)


def _escalate(action_type: str, risk_level: RiskLevel, description: str) -> ActionSpec:
    """ESC / DENY-ESC row: escalate for legal_admin, deny for everyone else."""
    return ActionSpec(
        target_system=TARGET_SYSTEM,
        action_type=action_type,
        risk_level=risk_level,
        verdict_privileged=PolicyVerdict.ESCALATE,
        verdict_default=PolicyVerdict.DENY,
        privileged_roles=_LEGAL_ADMIN,
        description=description,
    )


def _deny(action_type: str, risk_level: RiskLevel, description: str) -> ActionSpec:
    """DENY row: denied for every role, no privileged escape hatch."""
    return ActionSpec(
        target_system=TARGET_SYSTEM,
        action_type=action_type,
        risk_level=risk_level,
        verdict_privileged=PolicyVerdict.DENY,
        verdict_default=PolicyVerdict.DENY,
        privileged_roles=(),
        description=description,
    )


def _allow(action_type: str, risk_level: RiskLevel, description: str) -> ActionSpec:
    """Routine authorized read row: allow for legal_admin, deny for everyone else."""
    return ActionSpec(
        target_system=TARGET_SYSTEM,
        action_type=action_type,
        risk_level=risk_level,
        verdict_privileged=PolicyVerdict.ALLOW,
        verdict_default=PolicyVerdict.DENY,
        privileged_roles=_LEGAL_ADMIN,
        description=description,
    )


ACTIONS: tuple[ActionSpec, ...] = (
    _allow(
        "read_published_policy",
        RiskLevel.LOW,
        "Read a published internal policy document (read-only).",
    ),
    _escalate(
        "generate_or_send_contract",
        RiskLevel.HIGH,
        "Generate or send a contract to a counterparty.",
    ),
    _escalate(
        "modify_contract_clause",
        RiskLevel.HIGH,
        "Modify a clause in an existing contract.",
    ),
    _escalate(
        "delete_legal_document",
        RiskLevel.CRITICAL,
        "Delete a legal document from the document management system.",
    ),
    _escalate(
        "share_confidential_document",
        RiskLevel.HIGH,
        "Share a confidential document with an external party.",
    ),
    _escalate(
        "accept_contract_terms",
        RiskLevel.CRITICAL,
        "Accept contract terms on behalf of the organization.",
    ),
    _escalate(
        "submit_regulatory_document",
        RiskLevel.HIGH,
        "Submit a regulatory document to an authority.",
    ),
    _escalate(
        "modify_internal_policy",
        RiskLevel.HIGH,
        "Modify an internal company policy document.",
    ),
    _deny(
        "delete_evidence_item",
        RiskLevel.CRITICAL,
        "Delete an item held as legal evidence.",
    ),
    _escalate(
        "export_audit_file",
        RiskLevel.CRITICAL,
        "Export an audit file out of the system.",
    ),
)
