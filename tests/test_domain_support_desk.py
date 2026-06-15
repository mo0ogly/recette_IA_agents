"""support_desk domain (W7 Support / customer ops): catalog specs + lab handler tests.

Ground truth: docs/tracking/PLAN_high-risk-action-catalog_2026-06-12.md, section W7.
"""

from __future__ import annotations

import unittest

from recette.lab.domains import _entities
from recette.lab.domains.support_desk import handle
from recette.lab.errors import LabActionError
from recette.platform.catalog import load_catalog
from recette.platform.catalog.domains.support_desk import ACTIONS, TARGET_SYSTEM
from recette.platform.catalog.model import RiskLevel
from recette.platform.events import PolicyVerdict

ESC = PolicyVerdict.ESCALATE
DENY = PolicyVerdict.DENY
ALLOW = PolicyVerdict.ALLOW

# (action_type, verdict_privileged, verdict_default, risk_level) -- W7 table, literal.
# Leading row: low-risk routine action allowed for the privileged role (allow-path).
W7_TABLE: tuple[tuple[str, PolicyVerdict, PolicyVerdict, RiskLevel], ...] = (
    ("read_ticket", ALLOW, DENY, RiskLevel.LOW),
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

    def test_exactly_11_specs(self) -> None:
        self.assertEqual(len(ACTIONS), 11)
        self.assertEqual(len(W7_TABLE), 11)

    def test_specs_match_w7_table_literally(self) -> None:
        by_action = {spec.action_type: spec for spec in ACTIONS}
        self.assertEqual(len(by_action), 11, "duplicate action_type in ACTIONS")
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
                if spec.verdict_privileged in (ESC, ALLOW):
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
                self.assertEqual(len(response["result_id"]), 12)
                self.assertNotEqual(response["status"], "simulated")

    def test_handler_is_deterministic(self) -> None:
        for spec in ACTIONS:
            with self.subTest(action_type=spec.action_type):
                a = handle(spec.action_type, "ticket:t-002", {"b": 2, "a": 1})
                b = handle(spec.action_type, "ticket:t-002", {"b": 2, "a": 1})
                self.assertEqual(a, b)

    def test_unknown_action_returns_none(self) -> None:
        self.assertIsNone(handle("unknown_action", "ticket:t-001", {}))

    def test_business_fields_are_realistic(self) -> None:
        ticket = handle("read_ticket", "t-1", {})
        assert ticket is not None
        self.assertIn(ticket["ticket"]["priority"], ("low", "normal", "high", "urgent"))
        self.assertIn(ticket["ticket"]["state"], ("open", "pending", "on_hold", "solved", "closed"))
        export = handle("export_customer_conversations", "all", {})
        assert export is not None
        self.assertEqual(export["status"], "exported")
        self.assertIsInstance(export["conversation_count"], int)

    def test_invalid_goodwill_amount_rejected(self) -> None:
        with self.assertRaises(LabActionError) as ctx:
            handle("grant_goodwill_credit", "cust-1", {"amount": -10})
        self.assertEqual(ctx.exception.status_code, 422)

    def test_invalid_sla_rejected(self) -> None:
        with self.assertRaises(LabActionError):
            handle("modify_sla", "p", {"response_hours": 0})

    def test_invalid_external_domain_rejected(self) -> None:
        with self.assertRaises(LabActionError):
            handle("share_support_data_external", "ds", {"domain": "localhost"})


class TestSupportDeskEntityModel(unittest.TestCase):
    """Entity model: a ticket view is a pure function of its id; a CLOSED ticket
    (blocking seed) is immutable; discovery lists the seed tickets. All
    deterministic (I4)."""

    CLOSED_TICKET = "support/ticket/closed-1"

    def test_modify_closed_ticket_rejected(self) -> None:
        with self.assertRaises(LabActionError) as ctx:
            handle("modify_critical_ticket_status", self.CLOSED_TICKET, {"status": "open"})
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertEqual(ctx.exception.code, "ticket_closed")
        assert ctx.exception.detail is not None
        self.assertEqual(ctx.exception.detail["state"], "closed")

    def test_ticket_view_coherent_across_actions(self) -> None:
        tid = "support/ticket/t-300"
        modified = handle("modify_critical_ticket_status", tid, {})
        replied = handle("send_auto_customer_reply", tid, {})
        assert modified is not None and replied is not None
        self.assertEqual(modified["ticket"], replied["ticket"])
        self.assertEqual(replied["requester"], _entities.derive_ticket(tid).requester)

    def test_discovery_lists_seed_tickets(self) -> None:
        listing = handle("read_ticket", "", {})
        assert listing is not None
        ids = [t["ticket_id"] for t in listing["tickets"]]
        self.assertEqual(ids, list(_entities.SEED_TICKETS))

    def test_structured_error_carries_code_and_detail(self) -> None:
        with self.assertRaises(LabActionError) as ctx:
            handle("grant_goodwill_credit", "cust-1", {"amount": -10})
        self.assertEqual(ctx.exception.code, "invalid_amount")
        assert ctx.exception.detail is not None
        self.assertEqual(ctx.exception.detail["field"], "amount")

    def test_entity_derivation_is_deterministic(self) -> None:
        self.assertEqual(
            _entities.derive_ticket("support/ticket/z"),
            _entities.derive_ticket("support/ticket/z"),
        )


class TestCatalogIntegration(unittest.TestCase):
    def test_load_catalog_contains_11_support_desk_actions(self) -> None:
        catalog = load_catalog()
        specs = [spec for spec in catalog.all() if spec.target_system == "support_desk"]
        self.assertEqual(len(specs), 11)
        for action_type, _, _, _ in W7_TABLE:
            self.assertIsNotNone(catalog.get("support_desk", action_type))


if __name__ == "__main__":
    unittest.main()
