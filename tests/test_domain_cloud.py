"""cloud domain (W8 Cloud / infrastructure): catalog specs + lab handler tests.

Ground truth: docs/tracking/PLAN_high-risk-action-catalog_2026-06-12.md, section W8.
"""

from __future__ import annotations

import unittest

from recette.lab.domains import _entities
from recette.lab.domains.cloud import handle
from recette.lab.errors import LabActionError
from recette.platform.catalog import load_catalog
from recette.platform.catalog.domains.cloud import ACTIONS, TARGET_SYSTEM
from recette.platform.catalog.model import RiskLevel
from recette.platform.events import PolicyVerdict

ESC = PolicyVerdict.ESCALATE
DENY = PolicyVerdict.DENY
ALLOW = PolicyVerdict.ALLOW

# (action_type, verdict_privileged, verdict_default, risk_level) -- W8 table, literal.
# Leading row: low-risk routine action allowed for the privileged role (allow-path).
W8_TABLE: tuple[tuple[str, PolicyVerdict, PolicyVerdict, RiskLevel], ...] = (
    ("read_resource_inventory", ALLOW, DENY, RiskLevel.LOW),
    ("delete_database", ESC, DENY, RiskLevel.CRITICAL),
    ("delete_s3_bucket", ESC, DENY, RiskLevel.CRITICAL),
    ("make_bucket_public", ESC, DENY, RiskLevel.CRITICAL),
    ("modify_security_group", ESC, DENY, RiskLevel.CRITICAL),
    ("open_sensitive_port", ESC, DENY, RiskLevel.CRITICAL),
    ("delete_backups", DENY, DENY, RiskLevel.CRITICAL),
    ("modify_k8s_config", ESC, DENY, RiskLevel.HIGH),
    ("delete_critical_pod", ESC, DENY, RiskLevel.HIGH),
    ("deploy_unvalidated_image", ESC, DENY, RiskLevel.HIGH),
    ("modify_env_variable", ESC, DENY, RiskLevel.HIGH),
    ("delete_kms_key", DENY, DENY, RiskLevel.CRITICAL),
    ("modify_cloud_iam", ESC, DENY, RiskLevel.CRITICAL),
    ("isolate_host", ESC, DENY, RiskLevel.HIGH),
)


class TestCloudCatalog(unittest.TestCase):
    def test_target_system(self) -> None:
        self.assertEqual(TARGET_SYSTEM, "cloud")
        for spec in ACTIONS:
            self.assertEqual(spec.target_system, "cloud")

    def test_exactly_14_specs(self) -> None:
        self.assertEqual(len(ACTIONS), 14)
        self.assertEqual(len(W8_TABLE), 14)

    def test_specs_match_w8_table_literally(self) -> None:
        by_action = {spec.action_type: spec for spec in ACTIONS}
        self.assertEqual(len(by_action), 14, "duplicate action_type in ACTIONS")
        for action_type, verdict_priv, verdict_def, risk in W8_TABLE:
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
                    self.assertEqual(spec.privileged_roles, ("cloud_admin",))
                else:
                    self.assertEqual(spec.privileged_roles, ())

    def test_descriptions_present(self) -> None:
        for spec in ACTIONS:
            self.assertTrue(spec.description, f"empty description for {spec.action_type!r}")


class TestCloudLabHandler(unittest.TestCase):
    def test_handler_covers_every_cataloged_action(self) -> None:
        for spec in ACTIONS:
            with self.subTest(action_type=spec.action_type):
                response = handle(spec.action_type, "vpc:prod-eu-1", {"reason": "recette"})
                self.assertIsInstance(response, dict)
                assert response is not None
                self.assertEqual(response["action"], spec.action_type)
                self.assertEqual(response["resource"], "vpc:prod-eu-1")
                self.assertEqual(len(response["result_id"]), 12)
                self.assertNotEqual(response["status"], "simulated")

    def test_handler_is_deterministic(self) -> None:
        for spec in ACTIONS:
            with self.subTest(action_type=spec.action_type):
                a = handle(spec.action_type, "cluster:k8s-prod", {"b": 2, "a": 1})
                b = handle(spec.action_type, "cluster:k8s-prod", {"b": 2, "a": 1})
                self.assertEqual(a, b)

    def test_unknown_action_returns_none(self) -> None:
        self.assertIsNone(handle("unknown_action", "vpc:prod-eu-1", {}))

    def test_business_fields_are_realistic(self) -> None:
        inv = handle("read_resource_inventory", "account", {})
        assert inv is not None
        self.assertEqual(inv["region"], "eu-west-1")
        self.assertIsInstance(inv["resources"]["ec2"], int)
        kms = handle("delete_kms_key", "key-1", {})
        assert kms is not None
        self.assertEqual(kms["status"], "scheduled_for_deletion")
        self.assertEqual(kms["pending_window_days"], 7)

    def test_invalid_port_rejected(self) -> None:
        with self.assertRaises(LabActionError) as ctx:
            handle("open_sensitive_port", "sg-1", {"port": 70000})
        self.assertEqual(ctx.exception.status_code, 422)

    def test_valid_port_accepted(self) -> None:
        resp = handle("open_sensitive_port", "sg-1", {"port": 22})
        assert resp is not None
        self.assertEqual(resp["port"], 22)


class TestCloudEntityModel(unittest.TestCase):
    """Entity model: a cloud resource is a pure function of its id; a TERMINATED
    resource (blocking seed) cannot be deleted/modified; discovery lists the seed
    resources. Deterministic (I4)."""

    TERMINATED = "cloud/res/terminated-1"

    def test_delete_terminated_resource_rejected(self) -> None:
        with self.assertRaises(LabActionError) as ctx:
            handle("delete_database", self.TERMINATED, {})
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertEqual(ctx.exception.code, "instance_terminated")
        assert ctx.exception.detail is not None
        self.assertEqual(ctx.exception.detail["state"], "terminated")

    def test_resource_view_coherent_across_actions(self) -> None:
        rid = "cloud/res/r-1"
        a = handle("delete_database", rid, {})
        b = handle("modify_security_group", rid, {})
        assert a is not None and b is not None
        self.assertEqual(a["database"], b["security_group"])

    def test_discovery_lists_seed_resources(self) -> None:
        listing = handle("read_resource_inventory", "", {})
        assert listing is not None
        ids = [r["resource_id"] for r in listing["resources_list"]]
        self.assertEqual(ids, list(_entities.SEED_CLOUD_RESOURCES))

    def test_structured_error_carries_code_and_detail(self) -> None:
        with self.assertRaises(LabActionError) as ctx:
            handle("open_sensitive_port", "sg-1", {"port": 70000})
        self.assertEqual(ctx.exception.code, "invalid_port")
        assert ctx.exception.detail is not None
        self.assertEqual(ctx.exception.detail["field"], "port")

    def test_entity_derivation_is_deterministic(self) -> None:
        self.assertEqual(
            _entities.derive_cloud_resource("cloud/res/z"),
            _entities.derive_cloud_resource("cloud/res/z"),
        )


class TestCatalogIntegration(unittest.TestCase):
    def test_load_catalog_contains_13_cloud_actions(self) -> None:
        catalog = load_catalog()
        cloud_specs = [spec for spec in catalog.all() if spec.target_system == "cloud"]
        self.assertEqual(len(cloud_specs), 14)
        for action_type, _, _, _ in W8_TABLE:
            self.assertIsNotNone(catalog.get("cloud", action_type))


if __name__ == "__main__":
    unittest.main()
