"""data_platform domain tests -- W5 table conformance, lab handler determinism (I4)."""

from __future__ import annotations

import unittest

from recette.lab.domains.data_platform import handle
from recette.platform.catalog import load_catalog
from recette.platform.catalog.domains.data_platform import ACTIONS, TARGET_SYSTEM
from recette.platform.catalog.model import RiskLevel
from recette.platform.events import PolicyVerdict

# W5 table from docs/tracking/PLAN_high-risk-action-catalog_2026-06-12.md.
# Row format: (action_type, verdict column, risk).
_W5_TABLE: tuple[tuple[str, str, RiskLevel], ...] = (
    ("export_customer_data", "ESC", RiskLevel.CRITICAL),
    ("download_full_database", "DENY/ESC", RiskLevel.CRITICAL),
    ("share_pii_file", "ESC", RiskLevel.CRITICAL),
    ("send_data_to_external_domain", "DENY/ESC", RiskLevel.CRITICAL),
    ("modify_retention_policy", "DENY/ESC", RiskLevel.CRITICAL),
    ("delete_logs", "DENY", RiskLevel.CRITICAL),
    ("delete_audit_evidence", "DENY", RiskLevel.CRITICAL),
    ("access_hr_data", "ESC", RiskLevel.HIGH),
    ("access_medical_data", "DENY/ESC", RiskLevel.CRITICAL),
    ("access_sensitive_financial_data", "ESC", RiskLevel.CRITICAL),
    ("extract_data_to_external_llm", "DENY/ESC", RiskLevel.CRITICAL),
)


class TestDataPlatformCatalog(unittest.TestCase):
    def test_target_system(self) -> None:
        self.assertEqual(TARGET_SYSTEM, "data_platform")

    def test_actions_match_w5_table(self) -> None:
        self.assertEqual(len(ACTIONS), len(_W5_TABLE))
        for spec, (action_type, verdict_column, risk) in zip(ACTIONS, _W5_TABLE, strict=True):
            with self.subTest(action_type=action_type):
                self.assertEqual(spec.target_system, "data_platform")
                self.assertEqual(spec.action_type, action_type)
                self.assertIs(spec.risk_level, risk)
                if verdict_column == "DENY":
                    self.assertIs(spec.verdict_privileged, PolicyVerdict.DENY)
                    self.assertIs(spec.verdict_default, PolicyVerdict.DENY)
                    self.assertEqual(spec.privileged_roles, ())
                else:  # ESC and DENY/ESC rows share the same mapping
                    self.assertIs(spec.verdict_privileged, PolicyVerdict.ESCALATE)
                    self.assertIs(spec.verdict_default, PolicyVerdict.DENY)
                    self.assertEqual(spec.privileged_roles, ("data_admin",))

    def test_descriptions_present(self) -> None:
        for spec in ACTIONS:
            with self.subTest(action_type=spec.action_type):
                self.assertTrue(spec.description)

    def test_load_catalog_contains_data_platform_actions(self) -> None:
        catalog = load_catalog()
        for action_type, _verdict, _risk in _W5_TABLE:
            with self.subTest(action_type=action_type):
                spec = catalog.get("data_platform", action_type)
                self.assertIsNotNone(spec)
        found = [s for s in catalog.all() if s.target_system == "data_platform"]
        self.assertEqual(len(found), 11)


class TestDataPlatformLabHandler(unittest.TestCase):
    def test_handler_covers_every_spec(self) -> None:
        for spec in ACTIONS:
            with self.subTest(action_type=spec.action_type):
                response = handle(spec.action_type, "res-1", {"k": "v"})
                self.assertIsInstance(response, dict)
                assert response is not None  # narrow for type-checkers
                self.assertEqual(response["action"], spec.action_type)
                self.assertEqual(response["resource"], "res-1")
                self.assertEqual(response["status"], "simulated")
                self.assertEqual(len(response["result_id"]), 12)

    def test_handler_is_deterministic(self) -> None:
        payload = {"b": 2, "a": 1}
        for spec in ACTIONS:
            with self.subTest(action_type=spec.action_type):
                first = handle(spec.action_type, "res-x", payload)
                second = handle(spec.action_type, "res-x", payload)
                self.assertEqual(first, second)

    def test_handler_result_id_depends_on_inputs(self) -> None:
        a = handle("delete_logs", "res-1", {})
        b = handle("delete_logs", "res-2", {})
        assert a is not None and b is not None
        self.assertNotEqual(a["result_id"], b["result_id"])

    def test_unknown_action_returns_none(self) -> None:
        self.assertIsNone(handle("not_in_catalog", "res-1", {}))
        self.assertIsNone(handle("", "res-1", {}))


if __name__ == "__main__":
    unittest.main()
