"""crm domain tests: W3 catalog specs and lab handler determinism."""

from __future__ import annotations

import hashlib
import json
import unittest

from recette.lab.domains import _entities
from recette.lab.domains import crm as crm_lab
from recette.lab.errors import LabActionError
from recette.platform.catalog import load_catalog
from recette.platform.catalog.domains.crm import ACTIONS, TARGET_SYSTEM
from recette.platform.catalog.model import RiskLevel
from recette.platform.events import PolicyVerdict

# Literal copy of the "### W3" table in
# docs/tracking/PLAN_high-risk-action-catalog_2026-06-12.md:
# (action_type, plan verdict column, risk column).
W3_TABLE: tuple[tuple[str, str, RiskLevel], ...] = (
    ("read_contact_record", "ALLOW", RiskLevel.LOW),
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
        # ALLOW row -> privileged role allowed (low-risk routine); ESC / DENY/ESC
        # rows -> privileged role escalates (I6); any other role denied by default.
        expected = {
            "ALLOW": PolicyVerdict.ALLOW,
            "ESC": PolicyVerdict.ESCALATE,
            "DENY/ESC": PolicyVerdict.ESCALATE,
        }
        for spec, (_action, verdict, _risk) in zip(ACTIONS, W3_TABLE, strict=True):
            with self.subTest(action=spec.action_type):
                self.assertIn(verdict, expected)
                self.assertIs(spec.verdict_privileged, expected[verdict])
                self.assertIs(spec.verdict_default, PolicyVerdict.DENY)
                self.assertEqual(spec.privileged_roles, ("sales_admin",))
                self.assertEqual(spec.target_system, "crm")
                self.assertTrue(spec.description)

    def test_load_catalog_contains_the_eleven_crm_actions(self) -> None:
        catalog = load_catalog()
        crm_specs = tuple(spec for spec in catalog.all() if spec.target_system == "crm")
        self.assertEqual(len(crm_specs), 11)
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
                self.assertEqual(len(response["result_id"]), 12)
                # Realistic, action-specific status (no generic "simulated" blob).
                self.assertNotEqual(response["status"], "simulated")

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


class TestCrmRealism(unittest.TestCase):
    def test_business_fields_are_realistic(self) -> None:
        contact = crm_lab.handle("read_contact_record", "alice", {})
        assert contact is not None
        self.assertTrue(contact["contact"]["id"].startswith("cnt_"))
        self.assertIn("@", contact["contact"]["email"])
        self.assertIn(
            contact["contact"]["lifecycle_stage"],
            ("lead", "mql", "sql", "customer", "churned"),
        )
        export = crm_lab.handle("export_customer_base", "all", {})
        assert export is not None
        self.assertEqual(export["status"], "exported")
        self.assertIsInstance(export["row_count"], int)

    def test_invalid_opportunity_amount_rejected(self) -> None:
        with self.assertRaises(LabActionError) as ctx:
            crm_lab.handle("change_opportunity_amounts", "opp-1", {"amount": -3})
        self.assertEqual(ctx.exception.status_code, 422)

    def test_unknown_currency_rejected(self) -> None:
        with self.assertRaises(LabActionError):
            crm_lab.handle("change_opportunity_amounts", "opp-1", {"amount": 10, "currency": "XXX"})

    def test_amount_omitted_is_lenient(self) -> None:
        resp = crm_lab.handle("change_opportunity_amounts", "opp-1", {})
        assert resp is not None
        self.assertRegex(resp["amount"], r"^\d+\.\d{2}$")


class TestCrmEntityModel(unittest.TestCase):
    """Entity model: opportunity/contact/account views are pure functions of the
    id; a closed-won opportunity's amount cannot be changed; discovery lists the
    seed contacts. All deterministic (I4)."""

    CLOSED_OPP = "crm/opp/closed-1"

    def test_change_amount_on_closed_opportunity_rejected(self) -> None:
        with self.assertRaises(LabActionError) as ctx:
            crm_lab.handle("change_opportunity_amounts", self.CLOSED_OPP, {"amount": 100})
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertEqual(ctx.exception.code, "opportunity_closed")
        assert ctx.exception.detail is not None
        self.assertEqual(ctx.exception.detail["stage"], "closed_won")

    def test_open_opportunity_amount_defaults_to_entity(self) -> None:
        # A no-amount change uses the opportunity's derived amount (coherence).
        opp = _entities.derive_opportunity("crm/opp/open-1")
        resp = crm_lab.handle("change_opportunity_amounts", "crm/opp/open-1", {})
        assert resp is not None
        self.assertEqual(resp["amount"], opp.amount)
        self.assertEqual(resp["currency"], opp.currency)

    def test_account_owner_is_coherent(self) -> None:
        account = _entities.derive_sales_account("crm/account/strategic-1")
        resp = crm_lab.handle(
            "change_strategic_account_owner", "crm/account/strategic-1", {"owner": "usr_new"}
        )
        assert resp is not None
        self.assertEqual(resp["old_owner"], account.owner)
        self.assertEqual(resp["new_owner"], "usr_new")

    def test_discovery_lists_seed_contacts(self) -> None:
        listing = crm_lab.handle("read_contact_record", "", {})
        assert listing is not None
        ids = [c["account"] for c in listing["contacts"]]
        self.assertEqual(ids, list(_entities.SEED_CONTACTS))

    def test_structured_error_carries_code_and_detail(self) -> None:
        with self.assertRaises(LabActionError) as ctx:
            crm_lab.handle("change_opportunity_amounts", "opp-1", {"amount": -3})
        self.assertEqual(ctx.exception.code, "invalid_amount")
        assert ctx.exception.detail is not None
        self.assertEqual(ctx.exception.detail["field"], "amount")

    def test_entity_derivation_is_deterministic(self) -> None:
        self.assertEqual(
            _entities.derive_opportunity("crm/opp/z"), _entities.derive_opportunity("crm/opp/z")
        )


if __name__ == "__main__":
    unittest.main()
