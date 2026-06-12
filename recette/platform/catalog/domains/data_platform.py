"""data_platform domain action specs -- W5 Data / confidentiality (11 actions).

Source of truth: docs/tracking/PLAN_high-risk-action-catalog_2026-06-12.md, section W5.
Verdict mapping convention:
- ESC and DENY/ESC rows: privileged role escalates, any other role is denied
  (deny-by-default), privileged_roles = ("data_admin",).
- DENY rows (delete_logs, delete_audit_evidence): denied for every role,
  privileged_roles = ().
"""

from __future__ import annotations

from ...events import PolicyVerdict
from ..model import ActionSpec, RiskLevel

TARGET_SYSTEM = "data_platform"

_DATA_ADMIN = ("data_admin",)


def _escalate(action_type: str, risk_level: RiskLevel, description: str) -> ActionSpec:
    """ESC / DENY-ESC row: escalate for data_admin, deny for everyone else."""
    return ActionSpec(
        target_system=TARGET_SYSTEM,
        action_type=action_type,
        risk_level=risk_level,
        verdict_privileged=PolicyVerdict.ESCALATE,
        verdict_default=PolicyVerdict.DENY,
        privileged_roles=_DATA_ADMIN,
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
    _escalate(
        "export_customer_data",
        RiskLevel.CRITICAL,
        "Export customer data out of the data platform.",
    ),
    _escalate(
        "download_full_database",
        RiskLevel.CRITICAL,
        "Download a full copy of a production database.",
    ),
    _escalate(
        "share_pii_file",
        RiskLevel.CRITICAL,
        "Share a file containing personally identifiable information.",
    ),
    _escalate(
        "send_data_to_external_domain",
        RiskLevel.CRITICAL,
        "Send internal data to an external domain.",
    ),
    _escalate(
        "modify_retention_policy",
        RiskLevel.CRITICAL,
        "Modify the data retention policy.",
    ),
    _deny(
        "delete_logs",
        RiskLevel.CRITICAL,
        "Delete platform logs.",
    ),
    _deny(
        "delete_audit_evidence",
        RiskLevel.CRITICAL,
        "Delete audit evidence records.",
    ),
    _escalate(
        "access_hr_data",
        RiskLevel.HIGH,
        "Access human resources data.",
    ),
    _escalate(
        "access_medical_data",
        RiskLevel.CRITICAL,
        "Access medical records data.",
    ),
    _escalate(
        "access_sensitive_financial_data",
        RiskLevel.CRITICAL,
        "Access sensitive financial data.",
    ),
    _escalate(
        "extract_data_to_external_llm",
        RiskLevel.CRITICAL,
        "Extract internal data into an external LLM service.",
    ),
)
