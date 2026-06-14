"""compliance domain action specs -- regulatory / KYC workflows.

A governed compliance system (KYC review workflows), promoted from the BNP
scenario EXTRA_SPECS into the committed catalog. The privileged role is
compliance_admin; the single sensitive action escalates for it and is denied for
everyone else (deny-by-default). Criticality (Annex C axis) is the AgentRail
default posture; see catalog/model.py::Criticality.
"""

from __future__ import annotations

from ...events import PolicyVerdict
from ..model import ActionSpec, Criticality, RiskLevel

TARGET_SYSTEM = "compliance"

_COMPLIANCE_ADMIN = ("compliance_admin",)


def _escalate(
    action_type: str, criticality: Criticality, risk_level: RiskLevel, description: str
) -> ActionSpec:
    """ESC row: escalate for compliance_admin, deny for everyone else (deny-by-default)."""
    return ActionSpec(
        target_system=TARGET_SYSTEM,
        action_type=action_type,
        risk_level=risk_level,
        criticality=criticality,
        verdict_privileged=PolicyVerdict.ESCALATE,
        verdict_default=PolicyVerdict.DENY,
        privileged_roles=_COMPLIANCE_ADMIN,
        description=description,
    )


ACTIONS: tuple[ActionSpec, ...] = (
    _escalate(
        "open_kyc_review",
        Criticality.C3,
        RiskLevel.MEDIUM,
        "Open a KYC compliance review workflow.",
    ),
)
