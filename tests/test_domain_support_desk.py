"""support_desk domain (W7 Support / customer ops): catalog specs + lab handler tests.

Ground truth: docs/tracking/PLAN_high-risk-action-catalog_2026-06-12.md, section W7.
"""

from __future__ import annotations

import unittest

from recette.lab.domains.support_desk import handle
from recette.platform.catalog import load_catalog
from recette.platform.catalog.domains.support_desk import ACTIONS, TARGET_SYSTEM
from recette.platform.catalog.model import RiskLevel
from recette.platform.events import PolicyVerdict

ESC = PolicyVerdict.ESCALATE
DENY = PolicyVerdict.DENY

# (action_type, verdict_privileged, verdict_default, risk_level) -- W7 table, literal.
W7_TABLE: tuple[tuple[str, PolicyVerdict, PolicyVerdict, RiskLevel], ...] = (
    ("bulk_close_tickets", ESC, DENY, RiskLevel.MEDIUM),
    ("modify_critical_ticket_status", ESC, DENY, RiskLevel.MEDIUM),
    ("send_auto_customer_reply", ESC, DENY, RiskLevel.MEDIUM),
    ("grant_goodwill_credit", ESC, DENY, RiskLevel.HIGH),
    ("delete_ticket", ESC, DENY, RiskLevel.HIGH),
    ("export_customer_conversations", ESC, DENY, RiskLevel.CRITICAL),
    ("modify_sla", ESC, DENY, RiskLevel.HIGH),
    ("reassign_ticket_volume", ESC, DENY, RiskLevel.MEDIUM),
    ("access_vip_tickets", ESC, DENY, RiskLevel.HIGH),
    ("share_support_data_external", ESC, DENY, RiskLevel.HIGH),
)


class TestSupportDeskCatalog(unittest.TestCase):
    def test_target_system(self) -> None:
        self.assertEqual(TARGET_SYSTEM, "support_desk")
        for spec in ACTIONS:
            self.assertEqual(spec.target_system, "support_desk")

    def test_exactly_10_specs(self) -> None:
        self.assertEqual(len(ACTIONS), 10)
        self.assertEqual(len(W7_TABLE), 10)

    def test_specs_match_w7_table_literally(self) -> None:
        by_action = {spec.action_type: spec for spec in ACTIONS}
        self.assertEqual(len(by_action), 10, "duplicate action_type in ACTIONS")
        for action_type, verdict_priv, verdict_def, risk in W7_TABLE:
            with self.subTest(action_type=action_type):
                spec = by_action.get(action_type)
                self.assertIsNotNone(spec, f"missing action {action_type!r}")
                assert spec is not None
                self.assertIs(spec.verdict_privileged, verdict_priv)
                self.assertIs(spec.verdict_default, verdict_def)
                self.assertIs(spec.risk_level, risk)

    def test_privileged_roles_convention(self) -> None:
        for spec in ACTIONS:
            with self.subTest(action_type=spec.action_type):
                if spec.verdict_privileged is ESC:
                    self.assertEqual(spec.privileged_roles, ("support_admin",))
                else:
                    self.assertEqual(spec.privileged_roles, ())

    def test_descriptions_present(self) -> None:
        for spec in ACTIONS:
            self.assertTrue(spec.description, f"empty description for {spec.action_type!r}")


class TestSupportDeskLabHandler(unittest.TestCase):
    def test_handler_covers_every_cataloged_action(self) -> None:
        for spec in ACTIONS:
            with self.subTest(action_type=spec.action_type):
                response = handle(spec.action_type, "ticket:t-001", {"reason": "recette"})
                self.assertIsInstance(response, dict)
                assert response is not None
                self.assertEqual(response["action"], spec.action_type)
                self.assertEqual(response["resource"], "ticket:t-001")
                self.assertEqual(response["status"], "simulated")
                self.assertEqual(len(response["result_id"]), 12)

    def test_handler_is_deterministic(self) -> None:
        for spec in ACTIONS:
            with self.subTest(action_type=spec.action_type):
                a = handle(spec.action_type, "ticket:t-002", {"b": 2, "a": 1})
                b = handle(spec.action_type, "ticket:t-002", {"b": 2, "a": 1})
                self.assertEqual(a, b)

    def test_unknown_action_returns_none(self) -> None:
        self.assertIsNone(handle("unknown_action", "ticket:t-001", {}))


class TestCatalogIntegration(unittest.TestCase):
    def test_load_catalog_contains_10_support_desk_actions(self) -> None:
        catalog = load_catalog()
        specs = [spec for spec in catalog.all() if spec.target_system == "support_desk"]
        self.assertEqual(len(specs), 10)
        for action_type, _, _, _ in W7_TABLE:
            self.assertIsNotNone(catalog.get("support_desk", action_type))


if __name__ == "__main__":
    unittest.main()
