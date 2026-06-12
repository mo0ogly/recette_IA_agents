"""crm domain tests: W3 catalog specs and lab handler determinism."""

from __future__ import annotations

import hashlib
import json
import unittest

from recette.lab.domains import crm as crm_lab
from recette.platform.catalog import load_catalog
from recette.platform.catalog.domains.crm import ACTIONS, TARGET_SYSTEM
from recette.platform.catalog.model import RiskLevel
from recette.platform.events import PolicyVerdict

# Literal copy of the "### W3" table in
# docs/tracking/PLAN_high-risk-action-catalog_2026-06-12.md:
# (action_type, plan verdict column, risk column).
W3_TABLE: tuple[tuple[str, str, RiskLevel], ...] = (
    ("bulk_modify_contacts", "ESC", RiskLevel.HIGH),
    ("delete_contacts", "DENY/ESC", RiskLevel.HIGH),
    ("export_customer_base", "ESC", RiskLevel.CRITICAL),
    ("bulk_modify_deals", "ESC", RiskLevel.HIGH),
    ("change_strategic_account_owner", "ESC", RiskLevel.HIGH),
    ("modify_sales_pipeline", "ESC", RiskLevel.MEDIUM),
    ("send_mass_email", "ESC", RiskLevel.HIGH),
    ("change_opportunity_amounts", "ESC", RiskLevel.HIGH),
    ("modify_sensitive_fields", "ESC", RiskLevel.MEDIUM),
    ("sync_crm_to_external", "ESC", RiskLevel.HIGH),
)


class TestCrmCatalog(unittest.TestCase):
    def test_target_system(self) -> None:
        self.assertEqual(TARGET_SYSTEM, "crm")

    def test_actions_match_w3_table(self) -> None:
        self.assertEqual(
            tuple((spec.action_type, spec.risk_level) for spec in ACTIONS),
            tuple((action, risk) for action, _verdict, risk in W3_TABLE),
        )

    def test_verdict_mapping_convention(self) -> None:
        # Every W3 row is ESC or DENY/ESC: privileged role escalates (I6),
        # any other role is denied (deny-by-default).
        for spec, (_action, verdict, _risk) in zip(ACTIONS, W3_TABLE, strict=True):
            with self.subTest(action=spec.action_type):
                self.assertIn(verdict, ("ESC", "DENY/ESC"))
                self.assertIs(spec.verdict_privileged, PolicyVerdict.ESCALATE)
                self.assertIs(spec.verdict_default, PolicyVerdict.DENY)
                self.assertEqual(spec.privileged_roles, ("sales_admin",))
                self.assertEqual(spec.target_system, "crm")
                self.assertTrue(spec.description)

    def test_load_catalog_contains_the_ten_crm_actions(self) -> None:
        catalog = load_catalog()
        crm_specs = tuple(spec for spec in catalog.all() if spec.target_system == "crm")
        self.assertEqual(len(crm_specs), 10)
        for spec in ACTIONS:
            self.assertEqual(catalog.get("crm", spec.action_type), spec)


class TestCrmLabHandler(unittest.TestCase):
    def test_handler_covers_every_cataloged_action(self) -> None:
        for spec in ACTIONS:
            with self.subTest(action=spec.action_type):
                response = crm_lab.handle(spec.action_type, "account-42", {"key": "value"})
                self.assertIsInstance(response, dict)
                assert response is not None  # narrow Optional for the assertions below
                self.assertEqual(response["action"], spec.action_type)
                self.assertEqual(response["resource"], "account-42")
                self.assertEqual(response["status"], "simulated")
                self.assertEqual(len(response["result_id"]), 12)

    def test_handler_is_deterministic(self) -> None:
        first = crm_lab.handle("delete_contacts", "segment-7", {"ids": [3, 1, 2]})
        second = crm_lab.handle("delete_contacts", "segment-7", {"ids": [3, 1, 2]})
        self.assertEqual(first, second)

    def test_result_id_matches_sha256_recipe(self) -> None:
        payload = {"b": 2, "a": 1}
        response = crm_lab.handle("send_mass_email", "list-1", payload)
        assert response is not None
        material = f"crm:send_mass_email:list-1:{json.dumps(payload, sort_keys=True)}"
        expected = hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]
        self.assertEqual(response["result_id"], expected)

    def test_distinct_inputs_yield_distinct_result_ids(self) -> None:
        a = crm_lab.handle("bulk_modify_deals", "deal-1", {"stage": "won"})
        b = crm_lab.handle("bulk_modify_deals", "deal-2", {"stage": "won"})
        assert a is not None and b is not None
        self.assertNotEqual(a["result_id"], b["result_id"])

    def test_unknown_action_returns_none(self) -> None:
        self.assertIsNone(crm_lab.handle("read_contact", "contact-1", {}))
        self.assertIsNone(crm_lab.handle("", "contact-1", {}))


if __name__ == "__main__":
    unittest.main()
