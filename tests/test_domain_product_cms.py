"""Product/CMS domain (W11): catalog specs match the plan table, lab handler is deterministic."""

from __future__ import annotations

import unittest

from recette.lab.domains import product_cms as product_cms_lab
from recette.lab.errors import LabActionError
from recette.platform.catalog import load_catalog
from recette.platform.catalog.domains import product_cms as product_cms_catalog
from recette.platform.catalog.model import RiskLevel
from recette.platform.events import PolicyVerdict

# Literal copy of the W11 table from PLAN_high-risk-action-catalog_2026-06-12.md:
# (action_type, risk_level, verdict_privileged, verdict_default).
# ESC and DENY/ESC rows escalate for product_admin, deny by default; no pure DENY row.
W11_TABLE = (
    ("read_content_draft", RiskLevel.LOW, PolicyVerdict.ALLOW, PolicyVerdict.DENY),
    ("publish_production", RiskLevel.HIGH, PolicyVerdict.ESCALATE, PolicyVerdict.DENY),
    ("modify_public_page", RiskLevel.MEDIUM, PolicyVerdict.ESCALATE, PolicyVerdict.DENY),
    ("send_marketing_campaign", RiskLevel.HIGH, PolicyVerdict.ESCALATE, PolicyVerdict.DENY),
    ("modify_pricing", RiskLevel.HIGH, PolicyVerdict.ESCALATE, PolicyVerdict.DENY),
    ("delete_content", RiskLevel.MEDIUM, PolicyVerdict.ESCALATE, PolicyVerdict.DENY),
    ("change_product_config", RiskLevel.HIGH, PolicyVerdict.ESCALATE, PolicyVerdict.DENY),
    (
        "enable_feature_all_customers",
        RiskLevel.HIGH,
        PolicyVerdict.ESCALATE,
        PolicyVerdict.DENY,
    ),
    ("disable_critical_feature", RiskLevel.HIGH, PolicyVerdict.ESCALATE, PolicyVerdict.DENY),
    ("modify_user_onboarding", RiskLevel.MEDIUM, PolicyVerdict.ESCALATE, PolicyVerdict.DENY),
)


class TestProductCmsCatalog(unittest.TestCase):
    def test_target_system(self) -> None:
        self.assertEqual(product_cms_catalog.TARGET_SYSTEM, "product_cms")

    def test_actions_match_w11_table(self) -> None:
        self.assertEqual(len(product_cms_catalog.ACTIONS), len(W11_TABLE))
        for spec, row in zip(product_cms_catalog.ACTIONS, W11_TABLE, strict=True):
            action_type, risk_level, verdict_privileged, verdict_default = row
            with self.subTest(action_type=action_type):
                self.assertEqual(spec.action_type, action_type)
                self.assertEqual(spec.target_system, "product_cms")
                self.assertIs(spec.risk_level, risk_level)
                self.assertIs(spec.verdict_privileged, verdict_privileged)
                self.assertIs(spec.verdict_default, verdict_default)
                self.assertEqual(spec.privileged_roles, ("product_admin",))
                self.assertTrue(spec.description)

    def test_verdict_for_role(self) -> None:
        for spec in product_cms_catalog.ACTIONS:
            with self.subTest(action_type=spec.action_type):
                # privileged role gets the spec's privileged verdict (allow for the
                # low-risk routine action, escalate otherwise); other roles denied.
                self.assertIs(spec.verdict_for_role("product_admin"), spec.verdict_privileged)
                self.assertIs(spec.verdict_for_role("support_bot"), PolicyVerdict.DENY)


class TestProductCmsLabHandler(unittest.TestCase):
    def test_handler_covers_every_cataloged_action(self) -> None:
        for spec in product_cms_catalog.ACTIONS:
            with self.subTest(action_type=spec.action_type):
                response = product_cms_lab.handle(spec.action_type, "page-42", {"locale": "en"})
                self.assertIsInstance(response, dict)
                assert response is not None  # narrow type for the checks below
                self.assertEqual(response["action"], spec.action_type)
                self.assertEqual(response["resource"], "page-42")
                self.assertEqual(len(response["result_id"]), 12)
                self.assertNotEqual(response["status"], "simulated")

    def test_handler_is_deterministic(self) -> None:
        payload = {"plan": "pro", "amount": 49}
        first = product_cms_lab.handle("modify_pricing", "pricing-page", payload)
        second = product_cms_lab.handle("modify_pricing", "pricing-page", payload)
        self.assertEqual(first, second)

    def test_result_id_varies_with_input(self) -> None:
        a = product_cms_lab.handle("publish_production", "release-1", {"version": "1.0"})
        b = product_cms_lab.handle("publish_production", "release-1", {"version": "1.1"})
        assert a is not None and b is not None
        self.assertNotEqual(a["result_id"], b["result_id"])

    def test_unknown_action_returns_none(self) -> None:
        self.assertIsNone(product_cms_lab.handle("drop_database", "page-1", {}))
        self.assertIsNone(product_cms_lab.handle("", "page-1", {}))

    def test_business_fields_are_realistic(self) -> None:
        pub = product_cms_lab.handle("publish_production", "blog/post-1", {})
        assert pub is not None
        self.assertEqual(pub["status"], "published")
        self.assertTrue(pub["url"].startswith("https://"))
        feat = product_cms_lab.handle("enable_feature_all_customers", "new-ui", {})
        assert feat is not None
        self.assertEqual(feat["rollout"], "100%")
        self.assertIsInstance(feat["affected_customers"], int)

    def test_invalid_price_rejected(self) -> None:
        with self.assertRaises(LabActionError) as ctx:
            product_cms_lab.handle("modify_pricing", "plan-pro", {"price": -5})
        self.assertEqual(ctx.exception.status_code, 422)

    def test_unknown_currency_rejected(self) -> None:
        with self.assertRaises(LabActionError):
            product_cms_lab.handle("modify_pricing", "plan-pro", {"price": 10, "currency": "XXX"})


class TestProductCmsInLoadedCatalog(unittest.TestCase):
    def test_load_catalog_contains_the_10_product_cms_actions(self) -> None:
        catalog = load_catalog()
        self.assertIn("product_cms", catalog.target_systems())
        for row in W11_TABLE:
            action_type = row[0]
            with self.subTest(action_type=action_type):
                spec = catalog.get("product_cms", action_type)
                self.assertIsNotNone(spec)
        product_cms_specs = [s for s in catalog.all() if s.target_system == "product_cms"]
        self.assertEqual(len(product_cms_specs), 10)


if __name__ == "__main__":
    unittest.main()
