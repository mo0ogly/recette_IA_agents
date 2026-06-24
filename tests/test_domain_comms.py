"""comms domain (customer communication): catalog spec + lab handler tests.

comms is a promoted scenario domain (BANQUE fraud-investigation): one governed
outbound-notification action, escalate for comms_admin, deny otherwise.
"""

from __future__ import annotations

import unittest

from recette.lab.domains.comms import handle
from recette.platform.catalog import load_catalog
from recette.platform.catalog.domains.comms import ACTIONS, TARGET_SYSTEM
from recette.platform.catalog.model import Criticality, RiskLevel
from recette.platform.events import PolicyVerdict


class TestCommsCatalog(unittest.TestCase):
    def test_target_system(self) -> None:
        self.assertEqual(TARGET_SYSTEM, "comms")
        for spec in ACTIONS:
            self.assertEqual(spec.target_system, "comms")

    def test_single_governed_action(self) -> None:
        self.assertEqual(len(ACTIONS), 1)
        spec = ACTIONS[0]
        self.assertEqual(spec.action_type, "notify_customer")
        self.assertIs(spec.verdict_privileged, PolicyVerdict.ESCALATE)
        self.assertIs(spec.verdict_default, PolicyVerdict.DENY)
        self.assertIs(spec.risk_level, RiskLevel.MEDIUM)
        self.assertIs(spec.criticality, Criticality.C3)
        self.assertEqual(spec.privileged_roles, ("comms_admin",))

    def test_descriptions_present(self) -> None:
        for spec in ACTIONS:
            self.assertTrue(spec.description, f"empty description for {spec.action_type!r}")


class TestCommsLabHandler(unittest.TestCase):
    def test_handler_covers_every_cataloged_action(self) -> None:
        for spec in ACTIONS:
            with self.subTest(action_type=spec.action_type):
                response = handle(spec.action_type, "customer:c-001", {"channel": "sms"})
                self.assertIsInstance(response, dict)
                assert response is not None
                self.assertEqual(response["action"], spec.action_type)
                self.assertEqual(response["resource"], "customer:c-001")
                self.assertEqual(len(response["result_id"]), 12)
                self.assertNotEqual(response["status"], "simulated")

    def test_handler_is_deterministic(self) -> None:
        a = handle("notify_customer", "customer:c-002", {"b": 2, "a": 1})
        b = handle("notify_customer", "customer:c-002", {"b": 2, "a": 1})
        self.assertEqual(a, b)

    def test_unknown_action_returns_none(self) -> None:
        self.assertIsNone(handle("unknown_action", "customer:c-001", {}))


class TestCatalogIntegration(unittest.TestCase):
    def test_load_catalog_contains_comms(self) -> None:
        catalog = load_catalog()
        comms_specs = [s for s in catalog.all() if s.target_system == "comms"]
        self.assertEqual(len(comms_specs), 1)
        self.assertIsNotNone(catalog.get("comms", "notify_customer"))


if __name__ == "__main__":
    unittest.main()
