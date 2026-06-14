"""Finance domain (W4): catalog specs match the plan table, lab handler is a
realistic deterministic double (business fields + validation + coherence)."""

from __future__ import annotations

import unittest

from recette.lab.domains import finance as finance_lab
from recette.lab.errors import LabActionError
from recette.platform.catalog import load_catalog
from recette.platform.catalog.domains import finance as finance_catalog
from recette.platform.catalog.model import RiskLevel
from recette.platform.events import PolicyVerdict

# Literal copy of the W4 table from PLAN_high-risk-action-catalog_2026-06-12.md:
# (action_type, risk_level, verdict_privileged, verdict_default, privileged_roles).
# ESC and DENY/ESC rows escalate for finance_admin, deny by default; no pure DENY row.
W4_TABLE = (
    ("read_invoice_status", RiskLevel.LOW, PolicyVerdict.ALLOW, PolicyVerdict.DENY),
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
                # privileged role gets the spec's privileged verdict (allow for the
                # low-risk routine action, escalate otherwise); other roles denied.
                self.assertIs(spec.verdict_for_role("finance_admin"), spec.verdict_privileged)
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
                # Every action carries a stable 12-hex result_id and a realistic,
                # action-specific status (no generic "simulated" blob anymore).
                self.assertEqual(len(response["result_id"]), 12)
                self.assertNotEqual(response["status"], "simulated")

    def test_business_fields_are_realistic(self) -> None:
        pay = finance_lab.handle("create_payment", "acct-1", {"amount": 250, "currency": "USD"})
        assert pay is not None
        self.assertEqual(pay["status"], "pending_approval")
        self.assertTrue(pay["payment_id"].startswith("pay_"))
        self.assertEqual(pay["amount"], "250.00")
        self.assertEqual(pay["currency"], "USD")
        invoice = finance_lab.handle("read_invoice_status", "inv-9", {})
        assert invoice is not None
        self.assertIn(invoice["invoice_status"], ("paid", "pending", "overdue", "disputed"))

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

    def test_missing_optional_fields_are_lenient(self) -> None:
        # No amount/currency provided: a plausible value is derived, never an error,
        # so scenarios that omit fields still succeed.
        resp = finance_lab.handle("create_payment", "acct-1", {})
        assert resp is not None
        self.assertRegex(resp["amount"], r"^\d+\.\d{2}$")
        self.assertEqual(resp["currency"], "EUR")


class TestFinanceValidation(unittest.TestCase):
    def test_negative_amount_rejected(self) -> None:
        with self.assertRaises(LabActionError) as ctx:
            finance_lab.handle("create_payment", "acct-1", {"amount": -5})
        self.assertEqual(ctx.exception.status_code, 422)

    def test_unknown_currency_rejected(self) -> None:
        with self.assertRaises(LabActionError) as ctx:
            finance_lab.handle("trigger_refund", "inv-1", {"amount": 10, "currency": "XXX"})
        self.assertEqual(ctx.exception.status_code, 422)

    def test_malformed_iban_rejected(self) -> None:
        with self.assertRaises(LabActionError):
            finance_lab.handle("modify_iban", "acct-1", {"iban": "NOT-AN-IBAN"})

    def test_valid_iban_accepted_and_masked(self) -> None:
        # A structurally valid IBAN (ISO 13616 mod-97) passes and is masked.
        resp = finance_lab.handle("modify_iban", "acct-1", {"iban": "DE89370400440532013000"})
        assert resp is not None
        self.assertEqual(resp["status"], "updated")
        self.assertTrue(resp["iban"].startswith("DE"))
        self.assertTrue(resp["iban"].endswith("3000"))
        self.assertIn("*", resp["iban"])

    def test_numeric_string_amount_accepted(self) -> None:
        # LLMs often emit amounts as strings; a numeric string is accepted.
        resp = finance_lab.handle("create_payment", "acct-1", {"amount": "5000.00"})
        assert resp is not None
        self.assertEqual(resp["amount"], "5000.00")

    def test_placeholder_amount_rejected(self) -> None:
        # A non-numeric placeholder (observed real-AI output) is rejected, like
        # a real finance API would -- the realistic-double point.
        with self.assertRaises(LabActionError) as ctx:
            finance_lab.handle("launch_wire_transfer", "supplier", {"amount": "payment_amount"})
        self.assertEqual(ctx.exception.status_code, 422)

    def test_out_of_range_discount_rejected(self) -> None:
        with self.assertRaises(LabActionError):
            finance_lab.handle("apply_mass_discount", "catalog", {"discount_pct": 150})


class TestFinanceCoherence(unittest.TestCase):
    def test_add_payee_then_create_payment_is_coherent(self) -> None:
        # add_payee returns a payee_id; create_payment to THAT id is accepted.
        created = finance_lab.handle("add_payee", "supplier-x", {"iban": "DE89370400440532013000"})
        assert created is not None
        payee_id = created["payee_id"]
        paid = finance_lab.handle("create_payment", "acct-1", {"payee_id": payee_id, "amount": 10})
        assert paid is not None
        self.assertEqual(paid["payee"], payee_id)

    def test_fabricated_payee_rejected(self) -> None:
        with self.assertRaises(LabActionError) as ctx:
            finance_lab.handle("create_payment", "acct-1", {"payee_id": "payee_DOESNOTEXIST"})
        self.assertEqual(ctx.exception.status_code, 422)


class TestFinanceInLoadedCatalog(unittest.TestCase):
    def test_load_catalog_contains_the_13_finance_actions(self) -> None:
        catalog = load_catalog()
        self.assertIn("finance", catalog.target_systems())
        for row in W4_TABLE:
            action_type = row[0]
            with self.subTest(action_type=action_type):
                spec = catalog.get("finance", action_type)
                self.assertIsNotNone(spec)
        finance_specs = [s for s in catalog.all() if s.target_system == "finance"]
        self.assertEqual(len(finance_specs), 13)


if __name__ == "__main__":
    unittest.main()
