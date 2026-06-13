# tests/test_real_proxy.py
"""S2: real_saas proxy bridges the I5 protocol to a real forge.

RealForgeProxy adapts a forge to ExternalSystemProxy.execute(event): success ->
ok=True + side_effect_hash; an allowlist rejection, a blocked write, or any forge
error -> ok=False (fail-safe, never raises through, never bypasses).
"""

from __future__ import annotations

import unittest

from recette.events import AgentAction
from recette.platform.events import PlatformActionEvent
from recette.platform.proxy.real_proxy import RealForgeProxy
from recette.realmode import RealModeError


def _event(
    action_type: str = "read_repo",
    *,
    approval_state: str = "none",
    extra: dict | None = None,
) -> PlatformActionEvent:
    return PlatformActionEvent(
        event_id="evt-0001",
        timestamp="2026-06-13T00:00:00Z",
        agent_id="agent-bot",
        capability_scope=(),
        role="writer",
        action_type=action_type,
        target_system="github",
        resource="acme-test/widgets",
        payload={"title": "hi"},
        risk_score=1,
        risk_level="low",
        approval_state=approval_state,
        extra=extra or {},
    )


class _OkForge:
    def __init__(self) -> None:
        self.last_kwargs: dict | None = None

    def execute(self, **kwargs) -> AgentAction:  # noqa: ANN003
        self.last_kwargs = kwargs
        return AgentAction(
            event_id="evt-0001",
            seq=1,
            timestamp="2026-06-13T00:00:00Z",
            agent_id=kwargs["agent_id"],
            principal=kwargs["principal"],
            target_system=kwargs["target_system"],
            action_type=kwargs["action_type"],
            mode="read",
            resource=kwargs["resource"],
            approved=kwargs["approved"],
            params=kwargs["params"],
        )


class _AllowlistRejectForge:
    def execute(self, **kwargs):  # noqa: ANN003, ANN201
        raise RealModeError("resource not in allowlist")


class _WriteBlockedForge:
    def execute(self, **kwargs):  # noqa: ANN003, ANN201
        raise PermissionError("write action blocked (enable_writes=False)")


class RealForgeProxyTests(unittest.TestCase):
    def test_success_maps_to_ok_with_side_effect_hash(self) -> None:
        proxy = RealForgeProxy(_OkForge())
        result = proxy.execute(_event())
        self.assertTrue(result.ok)
        self.assertEqual(result.status_code, 200)
        self.assertIsNotNone(result.side_effect_hash)
        self.assertEqual(result.response["resource"], "acme-test/widgets")

    def test_side_effect_hash_is_deterministic(self) -> None:
        # Same event + same forge output -> identical hash (I4 / I1 audit).
        h1 = RealForgeProxy(_OkForge()).execute(_event()).side_effect_hash
        h2 = RealForgeProxy(_OkForge()).execute(_event()).side_effect_hash
        self.assertEqual(h1, h2)

    def test_allowlist_rejection_is_failsafe_not_raise(self) -> None:
        proxy = RealForgeProxy(_AllowlistRejectForge())
        result = proxy.execute(_event())
        self.assertFalse(result.ok)
        self.assertEqual(result.status_code, 502)
        self.assertIn("allowlist", result.error)

    def test_blocked_write_maps_to_forbidden(self) -> None:
        proxy = RealForgeProxy(_WriteBlockedForge())
        result = proxy.execute(_event(action_type="open_pr"))
        self.assertFalse(result.ok)
        self.assertEqual(result.status_code, 403)
        self.assertIn("refused", result.error)

    def test_principal_defaults_to_agent_id(self) -> None:
        forge = _OkForge()
        RealForgeProxy(forge).execute(_event())
        self.assertEqual(forge.last_kwargs["principal"], "agent-bot")

    def test_principal_from_event_extra_overrides_agent_id(self) -> None:
        forge = _OkForge()
        RealForgeProxy(forge).execute(_event(extra={"principal": "svc-account"}))
        self.assertEqual(forge.last_kwargs["principal"], "svc-account")

    def test_approval_state_drives_approved_flag(self) -> None:
        forge = _OkForge()
        RealForgeProxy(forge).execute(_event(approval_state="approved"))
        self.assertTrue(forge.last_kwargs["approved"])
        forge2 = _OkForge()
        RealForgeProxy(forge2).execute(_event(approval_state="pending"))
        self.assertFalse(forge2.last_kwargs["approved"])


if __name__ == "__main__":
    unittest.main()
