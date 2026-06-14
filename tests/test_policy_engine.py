"""Policy engine: pure, deny-by-default, role-sensitive verdicts."""

from __future__ import annotations

import unittest

from recette.platform.catalog import Catalog
from recette.platform.catalog.model import ActionSpec, RiskLevel
from recette.platform.events import PlatformActionEvent, PolicyVerdict
from recette.platform.policy.engine import decide
from recette.platform.policy.model import baseline_from_catalog

SPECS = (
    ActionSpec(
        target_system="okta",
        action_type="suspend_user",
        risk_level=RiskLevel.HIGH,
        verdict_privileged=PolicyVerdict.ESCALATE,
        verdict_default=PolicyVerdict.DENY,
        privileged_roles=("identity_admin",),
        description="Suspend an Okta user",
    ),
    ActionSpec(
        target_system="data_platform",
        action_type="delete_logs",
        risk_level=RiskLevel.CRITICAL,
        verdict_privileged=PolicyVerdict.DENY,  # pure DENY row: denied for everyone
        verdict_default=PolicyVerdict.DENY,
        privileged_roles=(),
        description="Delete logs",
    ),
)


def _event(target: str, action: str, role: str) -> PlatformActionEvent:
    return PlatformActionEvent(
        event_id="EV1",
        timestamp="2026-06-12T00:00:00Z",
        agent_id="agent-1",
        capability_scope=(),
        role=role,
        action_type=action,
        target_system=target,
        resource="r",
        payload={},
        risk_score=1,
        risk_level=str(RiskLevel.LOW),
    )


class TestPolicyEngine(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = Catalog(SPECS)
        self.policy = baseline_from_catalog(self.catalog, version="v-test")

    def test_privileged_role_escalates(self) -> None:
        d = decide(_event("okta", "suspend_user", "identity_admin"), self.policy, self.catalog)
        self.assertIs(d.verdict, PolicyVerdict.ESCALATE)
        self.assertEqual(d.policy_version, "v-test")
        self.assertEqual(d.rule_id, "okta.suspend_user.identity_admin")

    def test_unprivileged_role_denied(self) -> None:
        d = decide(_event("okta", "suspend_user", "marketing_bot"), self.policy, self.catalog)
        self.assertIs(d.verdict, PolicyVerdict.DENY)
        self.assertIsNone(d.rule_id)

    def test_pure_deny_row_denies_every_role(self) -> None:
        for role in ("identity_admin", "sre", "", "anything"):
            d = decide(_event("data_platform", "delete_logs", role), self.policy, self.catalog)
            self.assertIs(d.verdict, PolicyVerdict.DENY)

    def test_unknown_action_denied_critical(self) -> None:
        d = decide(_event("okta", "not_in_catalog", "identity_admin"), self.policy, self.catalog)
        self.assertIs(d.verdict, PolicyVerdict.DENY)
        self.assertIs(d.risk_level, RiskLevel.CRITICAL)

    def test_unknown_target_system_denied(self) -> None:
        d = decide(_event("mainframe", "anything", "root"), self.policy, self.catalog)
        self.assertIs(d.verdict, PolicyVerdict.DENY)

    def test_baseline_is_deterministic(self) -> None:
        a = baseline_from_catalog(self.catalog, version="v-test")
        b = baseline_from_catalog(self.catalog, version="v-test")
        self.assertEqual(a.to_dict(), b.to_dict())


if __name__ == "__main__":
    unittest.main()
