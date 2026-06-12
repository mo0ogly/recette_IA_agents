"""Finance domain (W4): catalog specs match the plan table, lab handler is deterministic."""

from __future__ import annotations

import unittest

from recette.lab.domains import finance as finance_lab
from recette.platform.catalog import load_catalog
from recette.platform.catalog.domains import finance as finance_catalog
from recette.platform.catalog.model import RiskLevel
from recette.platform.events import PolicyVerdict

# Literal copy of the W4 table from PLAN_high-risk-action-catalog_2026-06-12.md:
# (action_type, risk_level, verdict_privileged, verdict_default, privileged_roles).
# ESC and DENY/ESC rows escalate for finance_admin, deny by default; no pure DENY row.
W4_TABLE = (
    ("trigger_refund", RiskLevel.HIGH, PolicyVerdict.ESCALATE, PolicyVerdict.DENY),
    ("create_payment", RiskLevel.HIGH, PolicyVerdict.ESCALATE, PolicyVerdict.DENY),
    ("modify_iban", RiskLevel.CRITICAL, PolicyVerdict.ESCALATE, PolicyVerdict.DENY),
    ("add_payee", RiskLevel.CRITICAL, PolicyVerdict.ESCALATE, PolicyVerdict.DENY),
    ("validate_invoice", RiskLevel.HIGH, PolicyVerdict.ESCALATE, PolicyVerdict.DENY),
    (
        "modify_supplier_bank_details",
        RiskLevel.CRITICAL,
        PolicyVerdict.ESCALATE,
        PolicyVerdict.DENY,
    ),
    ("create_credit_note", RiskLevel.HIGH, PolicyVerdict.ESCALATE, PolicyVerdict.DENY),
    ("modify_price", RiskLevel.HIGH, PolicyVerdict.ESCALATE, PolicyVerdict.DENY),
    ("apply_mass_discount", RiskLevel.HIGH, PolicyVerdict.ESCALATE, PolicyVerdict.DENY),
    ("export_financial_data", RiskLevel.CRITICAL, PolicyVerdict.ESCALATE, PolicyVerdict.DENY),
    ("launch_wire_transfer", RiskLevel.CRITICAL, PolicyVerdict.ESCALATE, PolicyVerdict.DENY),
    ("modify_billing_rule", RiskLevel.HIGH, PolicyVerdict.ESCALATE, PolicyVerdict.DENY),
)


class TestFinanceCatalog(unittest.TestCase):
    def test_target_system(self) -> None:
        self.assertEqual(finance_catalog.TARGET_SYSTEM, "finance")

    def test_actions_match_w4_table(self) -> None:
        self.assertEqual(len(finance_catalog.ACTIONS), len(W4_TABLE))
        for spec, row in zip(finance_catalog.ACTIONS, W4_TABLE, strict=True):
            action_type, risk_level, verdict_privileged, verdict_default = row
            with self.subTest(action_type=action_type):
                self.assertEqual(spec.action_type, action_type)
                self.assertEqual(spec.target_system, "finance")
                self.assertIs(spec.risk_level, risk_level)
                self.assertIs(spec.verdict_privileged, verdict_privileged)
                self.assertIs(spec.verdict_default, verdict_default)
                self.assertEqual(spec.privileged_roles, ("finance_admin",))
                self.assertTrue(spec.description)

    def test_verdict_for_role(self) -> None:
        for spec in finance_catalog.ACTIONS:
            with self.subTest(action_type=spec.action_type):
                self.assertIs(spec.verdict_for_role("finance_admin"), PolicyVerdict.ESCALATE)
                self.assertIs(spec.verdict_for_role("marketing_bot"), PolicyVerdict.DENY)


class TestFinanceLabHandler(unittest.TestCase):
    def test_handler_covers_every_cataloged_action(self) -> None:
        for spec in finance_catalog.ACTIONS:
            with self.subTest(action_type=spec.action_type):
                response = finance_lab.handle(spec.action_type, "acct-42", {"amount": 100})
                self.assertIsInstance(response, dict)
                assert response is not None  # narrow type for the checks below
                self.assertEqual(response["action"], spec.action_type)
                self.assertEqual(response["resource"], "acct-42")
                self.assertEqual(response["status"], "simulated")
                self.assertEqual(len(response["result_id"]), 12)

    def test_handler_is_deterministic(self) -> None:
        payload = {"amount": 250, "currency": "EUR"}
        first = finance_lab.handle("launch_wire_transfer", "treasury-main", payload)
        second = finance_lab.handle("launch_wire_transfer", "treasury-main", payload)
        self.assertEqual(first, second)

    def test_result_id_varies_with_input(self) -> None:
        a = finance_lab.handle("create_payment", "acct-1", {"amount": 1})
        b = finance_lab.handle("create_payment", "acct-1", {"amount": 2})
        assert a is not None and b is not None
        self.assertNotEqual(a["result_id"], b["result_id"])

    def test_unknown_action_returns_none(self) -> None:
        self.assertIsNone(finance_lab.handle("mint_currency", "acct-1", {}))
        self.assertIsNone(finance_lab.handle("", "acct-1", {}))


class TestFinanceInLoadedCatalog(unittest.TestCase):
    def test_load_catalog_contains_the_12_finance_actions(self) -> None:
        catalog = load_catalog()
        self.assertIn("finance", catalog.target_systems())
        for row in W4_TABLE:
            action_type = row[0]
            with self.subTest(action_type=action_type):
                spec = catalog.get("finance", action_type)
                self.assertIsNotNone(spec)
        finance_specs = [s for s in catalog.all() if s.target_system == "finance"]
        self.assertEqual(len(finance_specs), 12)


if __name__ == "__main__":
    unittest.main()
