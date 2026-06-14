"""slack domain (W6): catalog specs match the plan table, lab handler is deterministic."""

from __future__ import annotations

import unittest

from recette.lab.domains import slack as slack_lab
from recette.lab.errors import LabActionError
from recette.platform.catalog import load_catalog
from recette.platform.catalog.domains import slack as slack_catalog
from recette.platform.catalog.model import RiskLevel
from recette.platform.events import PolicyVerdict

# Literal copy of the W6 table from
# docs/tracking/PLAN_high-risk-action-catalog_2026-06-12.md:
# (action_type, verdict column, risk column)
W6_TABLE = (
    ("read_public_channel", "ALLOW", RiskLevel.LOW),
    ("send_message_external_channel", "ESC", RiskLevel.MEDIUM),
    ("invite_external_user", "ESC", RiskLevel.HIGH),
    ("share_sensitive_file", "ESC", RiskLevel.HIGH),
    ("create_public_channel", "ESC", RiskLevel.MEDIUM),
    ("modify_workspace_permissions", "DENY/ESC", RiskLevel.HIGH),
    ("delete_channel", "ESC", RiskLevel.MEDIUM),
    ("publish_company_announcement", "ESC", RiskLevel.HIGH),
    ("send_message_as_executive", "DENY", RiskLevel.CRITICAL),
    ("access_confidential_channel", "DENY/ESC", RiskLevel.HIGH),
    ("export_slack_history", "ESC", RiskLevel.CRITICAL),
)


class TestSlackCatalog(unittest.TestCase):
    def test_target_system(self) -> None:
        self.assertEqual(slack_catalog.TARGET_SYSTEM, "slack")
        for spec in slack_catalog.ACTIONS:
            self.assertEqual(spec.target_system, "slack")

    def test_actions_match_w6_table(self) -> None:
        self.assertEqual(len(slack_catalog.ACTIONS), len(W6_TABLE))
        by_type = {spec.action_type: spec for spec in slack_catalog.ACTIONS}
        self.assertEqual(
            tuple(spec.action_type for spec in slack_catalog.ACTIONS),
            tuple(row[0] for row in W6_TABLE),
        )
        for action_type, verdict_col, risk in W6_TABLE:
            spec = by_type[action_type]
            self.assertIs(spec.risk_level, risk, action_type)
            if verdict_col == "ALLOW":  # low-risk routine action, allow-path
                self.assertIs(spec.verdict_privileged, PolicyVerdict.ALLOW, action_type)
                self.assertIs(spec.verdict_default, PolicyVerdict.DENY, action_type)
                self.assertEqual(spec.privileged_roles, ("workspace_admin",), action_type)
            elif verdict_col in ("ESC", "DENY/ESC"):
                self.assertIs(spec.verdict_privileged, PolicyVerdict.ESCALATE, action_type)
                self.assertIs(spec.verdict_default, PolicyVerdict.DENY, action_type)
                self.assertEqual(spec.privileged_roles, ("workspace_admin",), action_type)
            else:  # pure DENY row
                self.assertIs(spec.verdict_privileged, PolicyVerdict.DENY, action_type)
                self.assertIs(spec.verdict_default, PolicyVerdict.DENY, action_type)
                self.assertEqual(spec.privileged_roles, (), action_type)

    def test_descriptions_present(self) -> None:
        for spec in slack_catalog.ACTIONS:
            self.assertTrue(spec.description, spec.action_type)

    def test_verdict_for_role(self) -> None:
        by_type = {spec.action_type: spec for spec in slack_catalog.ACTIONS}
        esc = by_type["export_slack_history"]
        self.assertIs(esc.verdict_for_role("workspace_admin"), PolicyVerdict.ESCALATE)
        self.assertIs(esc.verdict_for_role("marketing_bot"), PolicyVerdict.DENY)
        deny = by_type["send_message_as_executive"]
        self.assertIs(deny.verdict_for_role("workspace_admin"), PolicyVerdict.DENY)
        self.assertIs(deny.verdict_for_role(""), PolicyVerdict.DENY)


class TestSlackLabHandler(unittest.TestCase):
    def test_handles_every_cataloged_action(self) -> None:
        for spec in slack_catalog.ACTIONS:
            response = slack_lab.handle(spec.action_type, "C0123GENERAL", {"k": "v"})
            self.assertIsInstance(response, dict, spec.action_type)
            assert response is not None  # narrow for type-checkers
            self.assertEqual(response["action"], spec.action_type)
            self.assertEqual(response["resource"], "C0123GENERAL")
            self.assertEqual(response["target_system"], "slack")
            self.assertEqual(len(response["result_id"]), 12)
            self.assertNotEqual(response["status"], "simulated")

    def test_deterministic(self) -> None:
        payload = {"text": "hello", "channel": "C42"}
        a = slack_lab.handle("delete_channel", "C42", payload)
        b = slack_lab.handle("delete_channel", "C42", dict(payload))
        self.assertEqual(a, b)
        # Key insertion order must not change the result (sort_keys).
        c = slack_lab.handle("delete_channel", "C42", {"channel": "C42", "text": "hello"})
        self.assertEqual(a, c)

    def test_different_inputs_different_result_id(self) -> None:
        a = slack_lab.handle("delete_channel", "C42", {})
        b = slack_lab.handle("delete_channel", "C43", {})
        assert a is not None and b is not None
        self.assertNotEqual(a["result_id"], b["result_id"])

    def test_unknown_action_returns_none(self) -> None:
        self.assertIsNone(slack_lab.handle("not_in_catalog", "C42", {}))
        self.assertIsNone(slack_lab.handle("", "C42", {}))

    def test_business_fields_are_realistic(self) -> None:
        chan = slack_lab.handle("read_public_channel", "general", {})
        assert chan is not None
        self.assertTrue(chan["channel"]["id"].startswith("C"))
        self.assertFalse(chan["channel"]["is_private"])
        exporting = slack_lab.handle("export_slack_history", "general", {})
        assert exporting is not None
        self.assertEqual(exporting["status"], "exported")
        self.assertIsInstance(exporting["message_count"], int)

    def test_invalid_invite_email_rejected(self) -> None:
        with self.assertRaises(LabActionError) as ctx:
            slack_lab.handle("invite_external_user", "general", {"email": "nope"})
        self.assertEqual(ctx.exception.status_code, 422)

    def test_invite_without_email_is_lenient(self) -> None:
        resp = slack_lab.handle("invite_external_user", "general", {})
        assert resp is not None
        self.assertIn("@", resp["email"])


class TestCatalogIntegration(unittest.TestCase):
    def test_load_catalog_contains_slack_actions(self) -> None:
        catalog = load_catalog()
        self.assertIn("slack", catalog.target_systems())
        slack_specs = [s for s in catalog.all() if s.target_system == "slack"]
        self.assertEqual(len(slack_specs), 11)
        for action_type, _verdict, _risk in W6_TABLE:
            self.assertIsNotNone(catalog.get("slack", action_type), action_type)


if __name__ == "__main__":
    unittest.main()
