"""product_cms domain action specs -- W11 Product / content (9 actions).

Source of truth: docs/tracking/PLAN_high-risk-action-catalog_2026-06-12.md, section W11.
Verdict mapping convention:
- ESC and DENY/ESC rows: privileged role escalates, any other role is denied
  (deny-by-default), privileged_roles = ("product_admin",).
- DENY rows: denied for every role, privileged_roles = () (none in W11).
"""

from __future__ import annotations

from ...events import PolicyVerdict
from ..model import ActionSpec, RiskLevel

TARGET_SYSTEM = "product_cms"

_PRODUCT_ADMIN = ("product_admin",)


def _escalate(action_type: str, risk_level: RiskLevel, description: str) -> ActionSpec:
    """ESC / DENY-ESC row: escalate for product_admin, deny for everyone else."""
    return ActionSpec(
        target_system=TARGET_SYSTEM,
        action_type=action_type,
        risk_level=risk_level,
        verdict_privileged=PolicyVerdict.ESCALATE,
        verdict_default=PolicyVerdict.DENY,
        privileged_roles=_PRODUCT_ADMIN,
        description=description,
    )


ACTIONS: tuple[ActionSpec, ...] = (
    _escalate(
        "publish_production",
        RiskLevel.HIGH,
        "Publish content or a release to the production environment.",
    ),
    _escalate("modify_public_page", RiskLevel.MEDIUM, "Modify a publicly visible page."),
    _escalate(
        "send_marketing_campaign",
        RiskLevel.HIGH,
        "Send a marketing campaign to customers.",
    ),
    _escalate("modify_pricing", RiskLevel.HIGH, "Modify the pricing displayed to customers."),
    _escalate("delete_content", RiskLevel.MEDIUM, "Delete existing content from the CMS."),
    _escalate(
        "change_product_config",
        RiskLevel.HIGH,
        "Change the configuration of a product.",
    ),
    _escalate(
        "enable_feature_all_customers",
        RiskLevel.HIGH,
        "Enable a feature for all customers at once.",
    ),
    _escalate(
        "disable_critical_feature",
        RiskLevel.HIGH,
        "Disable a critical feature of the product.",
    ),
    _escalate(
        "modify_user_onboarding",
        RiskLevel.MEDIUM,
        "Modify the user onboarding flow.",
    ),
)
