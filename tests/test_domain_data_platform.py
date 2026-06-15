"""data_platform domain tests -- W5 table conformance, lab handler determinism (I4)."""

from __future__ import annotations

import unittest

from recette.lab.domains import _entities
from recette.lab.domains.data_platform import handle
from recette.lab.errors import LabActionError
from recette.platform.catalog import load_catalog
from recette.platform.catalog.domains.data_platform import ACTIONS, TARGET_SYSTEM
from recette.platform.catalog.model import RiskLevel
from recette.platform.events import PolicyVerdict

# W5 table from docs/tracking/PLAN_high-risk-action-catalog_2026-06-12.md.
# Row format: (action_type, verdict column, risk).
_W5_TABLE: tuple[tuple[str, str, RiskLevel], ...] = (
    ("query_curated_dataset", "ALLOW", RiskLevel.LOW),
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
                if verdict_column == "ALLOW":  # low-risk routine action, allow-path
                    self.assertIs(spec.verdict_privileged, PolicyVerdict.ALLOW)
                    self.assertIs(spec.verdict_default, PolicyVerdict.DENY)
                    self.assertEqual(spec.privileged_roles, ("data_admin",))
                elif verdict_column == "DENY":
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
        self.assertEqual(len(found), 12)


class TestDataPlatformLabHandler(unittest.TestCase):
    def test_handler_covers_every_spec(self) -> None:
        for spec in ACTIONS:
            with self.subTest(action_type=spec.action_type):
                response = handle(spec.action_type, "res-1", {"k": "v"})
                self.assertIsInstance(response, dict)
                assert response is not None  # narrow for type-checkers
                self.assertEqual(response["action"], spec.action_type)
                self.assertEqual(response["resource"], "res-1")
                self.assertEqual(len(response["result_id"]), 12)
                self.assertNotEqual(response["status"], "simulated")

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


class TestDataPlatformRealism(unittest.TestCase):
    def test_business_fields_are_realistic(self) -> None:
        export = handle("export_customer_data", "customers", {})
        assert export is not None
        self.assertEqual(export["status"], "exported")
        self.assertTrue(export["contains_pii"])
        self.assertIsInstance(export["row_count"], int)
        med = handle("access_medical_data", "patient-7", {})
        assert med is not None
        self.assertEqual(med["classification"], "PHI")

    def test_invalid_recipient_rejected(self) -> None:
        with self.assertRaises(LabActionError) as ctx:
            handle("share_pii_file", "f-1", {"recipient": "not-email"})
        self.assertEqual(ctx.exception.status_code, 422)

    def test_invalid_external_domain_rejected(self) -> None:
        with self.assertRaises(LabActionError):
            handle("send_data_to_external_domain", "ds", {"domain": "localhost"})

    def test_invalid_retention_rejected(self) -> None:
        with self.assertRaises(LabActionError):
            handle("modify_retention_policy", "p", {"retention_days": -5})

    def test_omitted_fields_are_lenient(self) -> None:
        self.assertIsNotNone(handle("share_pii_file", "f-1", {}))
        self.assertIsNotNone(handle("send_data_to_external_domain", "ds", {}))
        self.assertIsNotNone(handle("modify_retention_policy", "p", {}))


class TestDataPlatformEntityModel(unittest.TestCase):
    """Entity model: a dataset is a pure function of its id; a FROZEN dataset
    (blocking seed) cannot be queried/exported; discovery lists the seed datasets.
    Deterministic (I4)."""

    FROZEN = "data/dataset/frozen-1"

    def test_query_frozen_dataset_rejected(self) -> None:
        with self.assertRaises(LabActionError) as ctx:
            handle("query_curated_dataset", self.FROZEN, {})
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertEqual(ctx.exception.code, "dataset_frozen")
        assert ctx.exception.detail is not None
        self.assertTrue(ctx.exception.detail["frozen"])

    def test_dataset_view_coherent_across_actions(self) -> None:
        did = "data/dataset/d-1"
        q = handle("query_curated_dataset", did, {})
        x = handle("export_customer_data", did, {})
        assert q is not None and x is not None
        self.assertEqual(q["classification"], x["classification"])

    def test_discovery_lists_seed_datasets(self) -> None:
        listing = handle("query_curated_dataset", "*", {})
        assert listing is not None
        ids = [d["dataset_id"] for d in listing["datasets"]]
        self.assertEqual(ids, list(_entities.SEED_DATASETS))

    def test_structured_error_carries_code_and_detail(self) -> None:
        with self.assertRaises(LabActionError) as ctx:
            handle("modify_retention_policy", "p", {"retention_days": -5})
        self.assertEqual(ctx.exception.code, "invalid_retention")
        assert ctx.exception.detail is not None
        self.assertEqual(ctx.exception.detail["field"], "retention_days")

    def test_entity_derivation_is_deterministic(self) -> None:
        self.assertEqual(
            _entities.derive_dataset("data/dataset/z"), _entities.derive_dataset("data/dataset/z")
        )


if __name__ == "__main__":
    unittest.main()
