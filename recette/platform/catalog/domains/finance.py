"""finance domain action specs -- W4 Finance / payments (12 actions).

Source of truth: docs/tracking/PLAN_high-risk-action-catalog_2026-06-12.md, section W4.
Verdict mapping convention:
- ESC and DENY/ESC rows: privileged role escalates, any other role is denied
  (deny-by-default), privileged_roles = ("finance_admin",).
- DENY rows: denied for every role, privileged_roles = () (none in W4).
"""

from __future__ import annotations

from ...events import PolicyVerdict
from ..model import ActionSpec, RiskLevel

TARGET_SYSTEM = "finance"

_FINANCE_ADMIN = ("finance_admin",)


def _escalate(action_type: str, risk_level: RiskLevel, description: str) -> ActionSpec:
    """ESC / DENY-ESC row: escalate for finance_admin, deny for everyone else."""
    return ActionSpec(
        target_system=TARGET_SYSTEM,
        action_type=action_type,
        risk_level=risk_level,
        verdict_privileged=PolicyVerdict.ESCALATE,
        verdict_default=PolicyVerdict.DENY,
        privileged_roles=_FINANCE_ADMIN,
        description=description,
    )


ACTIONS: tuple[ActionSpec, ...] = (
    _escalate("trigger_refund", RiskLevel.HIGH, "Trigger a refund on a customer payment."),
    _escalate("create_payment", RiskLevel.HIGH, "Create a new outgoing payment."),
    _escalate("modify_iban", RiskLevel.CRITICAL, "Modify the IBAN of a payee account."),
    _escalate("add_payee", RiskLevel.CRITICAL, "Add a new payee to the payment system."),
    _escalate("validate_invoice", RiskLevel.HIGH, "Validate an invoice for payment."),
    _escalate(
        "modify_supplier_bank_details",
        RiskLevel.CRITICAL,
        "Modify the bank details of a supplier.",
    ),
    _escalate("create_credit_note", RiskLevel.HIGH, "Create a credit note for a customer."),
    _escalate("modify_price", RiskLevel.HIGH, "Modify the price of a product or service."),
    _escalate(
        "apply_mass_discount",
        RiskLevel.HIGH,
        "Apply a discount to a large set of items at once.",
    ),
    _escalate(
        "export_financial_data",
        RiskLevel.CRITICAL,
        "Export financial data out of the system.",
    ),
    _escalate("launch_wire_transfer", RiskLevel.CRITICAL, "Launch an outgoing wire transfer."),
    _escalate("modify_billing_rule", RiskLevel.HIGH, "Modify an automated billing rule."),
)
