"""compliance domain (KYC / regulatory): catalog spec + lab handler tests.

compliance is a promoted scenario domain (BNP kyc-compliance): one governed
KYC-review action, escalate for compliance_admin, deny otherwise.
"""

from __future__ import annotations

import unittest

from recette.lab.domains.compliance import handle
from recette.platform.catalog import load_catalog
from recette.platform.catalog.domains.compliance import ACTIONS, TARGET_SYSTEM
from recette.platform.catalog.model import Criticality, RiskLevel
from recette.platform.events import PolicyVerdict


class TestComplianceCatalog(unittest.TestCase):
    def test_target_system(self) -> None:
        self.assertEqual(TARGET_SYSTEM, "compliance")
        for spec in ACTIONS:
            self.assertEqual(spec.target_system, "compliance")

    def test_single_governed_action(self) -> None:
        self.assertEqual(len(ACTIONS), 1)
        spec = ACTIONS[0]
        self.assertEqual(spec.action_type, "open_kyc_review")
        self.assertIs(spec.verdict_privileged, PolicyVerdict.ESCALATE)
        self.assertIs(spec.verdict_default, PolicyVerdict.DENY)
        self.assertIs(spec.risk_level, RiskLevel.MEDIUM)
        self.assertIs(spec.criticality, Criticality.C3)
        self.assertEqual(spec.privileged_roles, ("compliance_admin",))

    def test_descriptions_present(self) -> None:
        for spec in ACTIONS:
            self.assertTrue(spec.description, f"empty description for {spec.action_type!r}")


class TestComplianceLabHandler(unittest.TestCase):
    def test_handler_covers_every_cataloged_action(self) -> None:
        for spec in ACTIONS:
            with self.subTest(action_type=spec.action_type):
                response = handle(spec.action_type, "subject:s-001", {"tier": "enhanced"})
                self.assertIsInstance(response, dict)
                assert response is not None
                self.assertEqual(response["action"], spec.action_type)
                self.assertEqual(response["resource"], "subject:s-001")
                self.assertEqual(len(response["result_id"]), 12)
                self.assertNotEqual(response["status"], "simulated")

    def test_handler_is_deterministic(self) -> None:
        a = handle("open_kyc_review", "subject:s-002", {"b": 2, "a": 1})
        b = handle("open_kyc_review", "subject:s-002", {"b": 2, "a": 1})
        self.assertEqual(a, b)

    def test_unknown_action_returns_none(self) -> None:
        self.assertIsNone(handle("unknown_action", "subject:s-001", {}))


class TestCatalogIntegration(unittest.TestCase):
    def test_load_catalog_contains_compliance(self) -> None:
        catalog = load_catalog()
        specs = [s for s in catalog.all() if s.target_system == "compliance"]
        self.assertEqual(len(specs), 1)
        self.assertIsNotNone(catalog.get("compliance", "open_kyc_review"))


if __name__ == "__main__":
    unittest.main()
