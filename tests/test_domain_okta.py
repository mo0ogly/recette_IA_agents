"""okta domain (W1 Identity / Access): catalog specs + lab handler tests.

Ground truth: docs/tracking/PLAN_high-risk-action-catalog_2026-06-12.md, section W1.
"""

from __future__ import annotations

import unittest

from recette.lab.domains.okta import handle
from recette.lab.errors import LabActionError
from recette.platform.catalog import load_catalog
from recette.platform.catalog.domains.okta import ACTIONS, TARGET_SYSTEM
from recette.platform.catalog.model import RiskLevel
from recette.platform.events import PolicyVerdict

ESC = PolicyVerdict.ESCALATE
DENY = PolicyVerdict.DENY
ALLOW = PolicyVerdict.ALLOW

# (action_type, verdict_privileged, verdict_default, risk_level) -- W1 table, literal.
# The leading row is the low-risk routine action authorized for the privileged
# role (allow-path coverage, PLAN_APEX_catalog-allow-path_2026-06-14.md).
W1_TABLE: tuple[tuple[str, PolicyVerdict, PolicyVerdict, RiskLevel], ...] = (
    ("read_user_profile", ALLOW, DENY, RiskLevel.LOW),
    ("suspend_user", ESC, DENY, RiskLevel.HIGH),
    ("delete_user", ESC, DENY, RiskLevel.CRITICAL),
    ("reset_password", ESC, DENY, RiskLevel.HIGH),
    ("modify_user_roles", ESC, DENY, RiskLevel.HIGH),
    ("add_user_to_admin_group", ESC, DENY, RiskLevel.CRITICAL),
    ("create_api_key", ESC, DENY, RiskLevel.HIGH),
    ("revoke_api_key", ESC, DENY, RiskLevel.MEDIUM),
    ("revoke_token", ESC, DENY, RiskLevel.MEDIUM),
    ("generate_long_lived_token", ESC, DENY, RiskLevel.CRITICAL),
    ("modify_mfa_policy", ESC, DENY, RiskLevel.CRITICAL),
    ("disable_sso", DENY, DENY, RiskLevel.CRITICAL),
    ("add_oauth_app", ESC, DENY, RiskLevel.HIGH),
    ("modify_oauth_scopes", ESC, DENY, RiskLevel.HIGH),
    ("invite_external_user", ESC, DENY, RiskLevel.HIGH),
    ("revoke_long_lived_token", ESC, DENY, RiskLevel.HIGH),
    ("assume_delegation", DENY, DENY, RiskLevel.CRITICAL),
)


class TestOktaCatalog(unittest.TestCase):
    def test_target_system(self) -> None:
        self.assertEqual(TARGET_SYSTEM, "okta")
        for spec in ACTIONS:
            self.assertEqual(spec.target_system, "okta")

    def test_exactly_17_specs(self) -> None:
        self.assertEqual(len(ACTIONS), 17)
        self.assertEqual(len(W1_TABLE), 17)

    def test_specs_match_w1_table_literally(self) -> None:
        by_action = {spec.action_type: spec for spec in ACTIONS}
        self.assertEqual(len(by_action), 17, "duplicate action_type in ACTIONS")
        for action_type, verdict_priv, verdict_def, risk in W1_TABLE:
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
                    self.assertEqual(spec.privileged_roles, ("identity_admin",))
                else:
                    self.assertEqual(spec.privileged_roles, ())

    def test_descriptions_present(self) -> None:
        for spec in ACTIONS:
            self.assertTrue(spec.description, f"empty description for {spec.action_type!r}")


class TestOktaLabHandler(unittest.TestCase):
    def test_handler_covers_every_cataloged_action(self) -> None:
        for spec in ACTIONS:
            with self.subTest(action_type=spec.action_type):
                response = handle(spec.action_type, "user:u-001", {"reason": "recette"})
                self.assertIsInstance(response, dict)
                assert response is not None
                self.assertEqual(response["action"], spec.action_type)
                self.assertEqual(response["resource"], "user:u-001")
                self.assertEqual(len(response["result_id"]), 12)
                # Realistic, action-specific status (no generic "simulated" blob).
                self.assertNotEqual(response["status"], "simulated")

    def test_business_fields_are_realistic(self) -> None:
        profile = handle("read_user_profile", "alice", {})
        assert profile is not None
        self.assertTrue(profile["user"]["id"].startswith("00u"))
        self.assertIn("@", profile["user"]["email"])
        self.assertEqual(profile["user"]["status"], "ACTIVE")
        key = handle("create_api_key", "svc", {})
        assert key is not None
        self.assertTrue(key["key_id"].startswith("api"))
        self.assertEqual(key["status"], "ACTIVE")

    def test_handler_is_deterministic(self) -> None:
        for spec in ACTIONS:
            with self.subTest(action_type=spec.action_type):
                a = handle(spec.action_type, "user:u-002", {"b": 2, "a": 1})
                b = handle(spec.action_type, "user:u-002", {"b": 2, "a": 1})
                self.assertEqual(a, b)

    def test_unknown_action_returns_none(self) -> None:
        self.assertIsNone(handle("unknown_action", "user:u-001", {}))


class TestOktaValidation(unittest.TestCase):
    def test_invalid_email_rejected(self) -> None:
        with self.assertRaises(LabActionError) as ctx:
            handle("invite_external_user", "ext", {"email": "not-an-email"})
        self.assertEqual(ctx.exception.status_code, 422)
        # Structured refusal: machine-readable code + detail, like every domain.
        self.assertEqual(ctx.exception.code, "invalid_email")
        assert ctx.exception.detail is not None
        self.assertEqual(ctx.exception.detail["field"], "email")

    def test_valid_email_accepted(self) -> None:
        resp = handle("invite_external_user", "ext", {"email": "vendor@partner.com"})
        assert resp is not None
        self.assertEqual(resp["email"], "vendor@partner.com")
        self.assertEqual(resp["status"], "PENDING")

    def test_missing_email_is_lenient(self) -> None:
        resp = handle("invite_external_user", "ext", {})
        assert resp is not None
        self.assertIn("@", resp["email"])


class TestOktaCoherence(unittest.TestCase):
    def test_create_then_revoke_api_key_is_coherent(self) -> None:
        created = handle("create_api_key", "svc", {})
        assert created is not None
        key_id = created["key_id"]
        revoked = handle("revoke_api_key", "svc", {"key_id": key_id})
        assert revoked is not None
        self.assertEqual(revoked["key_id"], key_id)
        self.assertEqual(revoked["status"], "REVOKED")

    def test_fabricated_key_id_rejected(self) -> None:
        with self.assertRaises(LabActionError) as ctx:
            handle("revoke_api_key", "svc", {"key_id": "api_DOESNOTEXIST"})
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertEqual(ctx.exception.code, "unknown_api_key")
        assert ctx.exception.detail is not None
        self.assertEqual(ctx.exception.detail["field"], "api_key")

    def test_revoke_without_explicit_key_id_is_lenient(self) -> None:
        resp = handle("revoke_api_key", "svc", {})
        assert resp is not None
        self.assertTrue(resp["key_id"].startswith("api"))


class TestCatalogIntegration(unittest.TestCase):
    def test_load_catalog_contains_17_okta_actions(self) -> None:
        catalog = load_catalog()
        okta_specs = [spec for spec in catalog.all() if spec.target_system == "okta"]
        self.assertEqual(len(okta_specs), 17)
        for action_type, _, _, _ in W1_TABLE:
            self.assertIsNotNone(catalog.get("okta", action_type))


if __name__ == "__main__":
    unittest.main()
