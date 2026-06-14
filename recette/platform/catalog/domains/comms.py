"""comms domain action specs -- customer communication (incident/fraud workflows).

A governed customer-notification channel, distinct from the internal slack
workspace domain: comms covers outbound notifications to customers (e.g. a fraud
hold notice). Promoted from the BNP scenario EXTRA_SPECS into the committed
catalog. The privileged role is comms_admin; the single sensitive action
escalates for it and is denied for everyone else (deny-by-default). Criticality
(Annex C axis) is the AgentRail default posture; see catalog/model.py::Criticality.
"""

from __future__ import annotations

from ...events import PolicyVerdict
from ..model import ActionSpec, Criticality, RiskLevel

TARGET_SYSTEM = "comms"

_COMMS_ADMIN = ("comms_admin",)


def _escalate(
    action_type: str, criticality: Criticality, risk_level: RiskLevel, description: str
) -> ActionSpec:
    """ESC row: escalate for comms_admin, deny for everyone else (deny-by-default)."""
    return ActionSpec(
        target_system=TARGET_SYSTEM,
        action_type=action_type,
        risk_level=risk_level,
        criticality=criticality,
        verdict_privileged=PolicyVerdict.ESCALATE,
        verdict_default=PolicyVerdict.DENY,
        privileged_roles=_COMMS_ADMIN,
        description=description,
    )


ACTIONS: tuple[ActionSpec, ...] = (
    _escalate(
        "notify_customer",
        Criticality.C3,
        RiskLevel.MEDIUM,
        "Notify a customer via an authenticated channel.",
    ),
)
