"""HRIS domain (W9): catalog specs match the plan table, lab handler is deterministic."""

from __future__ import annotations

import unittest

from recette.lab.domains import hris as hris_lab
from recette.platform.catalog import load_catalog
from recette.platform.catalog.domains import hris as hris_catalog
from recette.platform.catalog.model import RiskLevel
from recette.platform.events import PolicyVerdict

# Literal copy of the W9 table from PLAN_high-risk-action-catalog_2026-06-12.md:
# (action_type, risk_level, verdict_privileged, verdict_default).
# ESC and DENY/ESC rows escalate for hr_admin, deny by default; no pure DENY row.
W9_TABLE = (
    ("modify_salary", RiskLevel.CRITICAL, PolicyVerdict.ESCALATE, PolicyVerdict.DENY),
    ("delete_employee", RiskLevel.HIGH, PolicyVerdict.ESCALATE, PolicyVerdict.DENY),
    ("change_contract_status", RiskLevel.HIGH, PolicyVerdict.ESCALATE, PolicyVerdict.DENY),
    ("access_sensitive_hr_records", RiskLevel.HIGH, PolicyVerdict.ESCALATE, PolicyVerdict.DENY),
    ("export_employee_data", RiskLevel.CRITICAL, PolicyVerdict.ESCALATE, PolicyVerdict.DENY),
    ("modify_leave", RiskLevel.MEDIUM, PolicyVerdict.ESCALATE, PolicyVerdict.DENY),
    ("create_employee_record", RiskLevel.MEDIUM, PolicyVerdict.ESCALATE, PolicyVerdict.DENY),
    ("send_official_hr_comm", RiskLevel.HIGH, PolicyVerdict.ESCALATE, PolicyVerdict.DENY),
    (
        "modify_employee_access_rights",
        RiskLevel.HIGH,
        PolicyVerdict.ESCALATE,
        PolicyVerdict.DENY,
    ),
)


class TestHrisCatalog(unittest.TestCase):
    def test_target_system(self) -> None:
        self.assertEqual(hris_catalog.TARGET_SYSTEM, "hris")

    def test_actions_match_w9_table(self) -> None:
        self.assertEqual(len(hris_catalog.ACTIONS), len(W9_TABLE))
        for spec, row in zip(hris_catalog.ACTIONS, W9_TABLE, strict=True):
            action_type, risk_level, verdict_privileged, verdict_default = row
            with self.subTest(action_type=action_type):
                self.assertEqual(spec.action_type, action_type)
                self.assertEqual(spec.target_system, "hris")
                self.assertIs(spec.risk_level, risk_level)
                self.assertIs(spec.verdict_privileged, verdict_privileged)
                self.assertIs(spec.verdict_default, verdict_default)
                self.assertEqual(spec.privileged_roles, ("hr_admin",))
                self.assertTrue(spec.description)

    def test_verdict_for_role(self) -> None:
        for spec in hris_catalog.ACTIONS:
            with self.subTest(action_type=spec.action_type):
                self.assertIs(spec.verdict_for_role("hr_admin"), PolicyVerdict.ESCALATE)
                self.assertIs(spec.verdict_for_role("marketing_bot"), PolicyVerdict.DENY)


class TestHrisLabHandler(unittest.TestCase):
    def test_handler_covers_every_cataloged_action(self) -> None:
        for spec in hris_catalog.ACTIONS:
            with self.subTest(action_type=spec.action_type):
                response = hris_lab.handle(spec.action_type, "emp-42", {"field": "value"})
                self.assertIsInstance(response, dict)
                assert response is not None  # narrow type for the checks below
                self.assertEqual(response["action"], spec.action_type)
                self.assertEqual(response["resource"], "emp-42")
                self.assertEqual(response["status"], "simulated")
                self.assertEqual(len(response["result_id"]), 12)

    def test_handler_is_deterministic(self) -> None:
        payload = {"salary": 65000, "currency": "EUR"}
        first = hris_lab.handle("modify_salary", "emp-7", payload)
        second = hris_lab.handle("modify_salary", "emp-7", payload)
        self.assertEqual(first, second)

    def test_result_id_varies_with_input(self) -> None:
        a = hris_lab.handle("create_employee_record", "emp-1", {"name": "a"})
        b = hris_lab.handle("create_employee_record", "emp-1", {"name": "b"})
        assert a is not None and b is not None
        self.assertNotEqual(a["result_id"], b["result_id"])

    def test_unknown_action_returns_none(self) -> None:
        self.assertIsNone(hris_lab.handle("fire_everyone", "emp-1", {}))
        self.assertIsNone(hris_lab.handle("", "emp-1", {}))


class TestHrisInLoadedCatalog(unittest.TestCase):
    def test_load_catalog_contains_the_9_hris_actions(self) -> None:
        catalog = load_catalog()
        self.assertIn("hris", catalog.target_systems())
        for row in W9_TABLE:
            action_type = row[0]
            with self.subTest(action_type=action_type):
                spec = catalog.get("hris", action_type)
                self.assertIsNotNone(spec)
        hris_specs = [s for s in catalog.all() if s.target_system == "hris"]
        self.assertEqual(len(hris_specs), 9)


if __name__ == "__main__":
    unittest.main()
