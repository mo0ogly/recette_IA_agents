"""hris domain action specs -- W9 HR (9 actions).

Source of truth: docs/tracking/PLAN_high-risk-action-catalog_2026-06-12.md, section W9.
Verdict mapping convention:
- ESC and DENY/ESC rows: privileged role escalates, any other role is denied
  (deny-by-default), privileged_roles = ("hr_admin",).
- DENY rows: denied for every role, privileged_roles = () (none in W9).
"""

from __future__ import annotations

from ...events import PolicyVerdict
from ..model import ActionSpec, RiskLevel

TARGET_SYSTEM = "hris"

_HR_ADMIN = ("hr_admin",)


def _escalate(action_type: str, risk_level: RiskLevel, description: str) -> ActionSpec:
    """ESC / DENY-ESC row: escalate for hr_admin, deny for everyone else."""
    return ActionSpec(
        target_system=TARGET_SYSTEM,
        action_type=action_type,
        risk_level=risk_level,
        verdict_privileged=PolicyVerdict.ESCALATE,
        verdict_default=PolicyVerdict.DENY,
        privileged_roles=_HR_ADMIN,
        description=description,
    )


def _allow(action_type: str, risk_level: RiskLevel, description: str) -> ActionSpec:
    """Routine authorized read row: allow for hr_admin, deny for everyone else."""
    return ActionSpec(
        target_system=TARGET_SYSTEM,
        action_type=action_type,
        risk_level=risk_level,
        verdict_privileged=PolicyVerdict.ALLOW,
        verdict_default=PolicyVerdict.DENY,
        privileged_roles=_HR_ADMIN,
        description=description,
    )


ACTIONS: tuple[ActionSpec, ...] = (
    _allow(
        "read_org_directory",
        RiskLevel.LOW,
        "Read the public employee directory (read-only, no sensitive records).",
    ),
    _escalate("modify_salary", RiskLevel.CRITICAL, "Modify the salary of an employee."),
    _escalate("delete_employee", RiskLevel.HIGH, "Delete an employee record from the HRIS."),
    _escalate(
        "change_contract_status",
        RiskLevel.HIGH,
        "Change the contract status of an employee.",
    ),
    _escalate(
        "access_sensitive_hr_records",
        RiskLevel.HIGH,
        "Access sensitive HR records of an employee.",
    ),
    _escalate(
        "export_employee_data",
        RiskLevel.CRITICAL,
        "Export employee data out of the HRIS.",
    ),
    _escalate("modify_leave", RiskLevel.MEDIUM, "Modify the leave balance or requests."),
    _escalate(
        "create_employee_record",
        RiskLevel.MEDIUM,
        "Create a new employee record in the HRIS.",
    ),
    _escalate(
        "send_official_hr_comm",
        RiskLevel.HIGH,
        "Send an official HR communication to employees.",
    ),
    _escalate(
        "modify_employee_access_rights",
        RiskLevel.HIGH,
        "Modify the access rights of an employee.",
    ),
)
