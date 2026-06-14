"""G5 RealSlackProxy live test against the REAL Slack Web API.

Skipped unless SLACK_BOT_TOKEN and INSPECT_IA_AGENTS_TEST_SLACK_CHANNEL are set (a bot
token with channels:read and a test channel id the bot is in). READ-only by
default (conversations.info) so the test never posts to a workspace; the write
path stays behind enable_writes and is not exercised here."""

from __future__ import annotations

import os
import unittest

from recette.platform.events import ApprovalState, PlatformActionEvent
from recette.platform.proxy.real_slack_proxy import RealSlackProxy

_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
_CHANNEL = os.environ.get("INSPECT_IA_AGENTS_TEST_SLACK_CHANNEL")


def _event(action_type: str, resource: str):
    return PlatformActionEvent(
        event_id="EVlive",
        timestamp="2026-06-13T00:00:00Z",
        agent_id="agent-live",
        capability_scope=("slack",),
        role="workspace_admin",
        action_type=action_type,
        target_system="slack",
        resource=resource,
        payload={},
        risk_score=3,
        risk_level="high",
        approval_state=ApprovalState.APPROVED,
    )


@unittest.skipUnless(
    _TOKEN and _CHANNEL, "needs SLACK_BOT_TOKEN + INSPECT_IA_AGENTS_TEST_SLACK_CHANNEL"
)
class RealSlackLiveTest(unittest.TestCase):
    def test_read_channel_info_against_real_slack(self) -> None:
        proxy = RealSlackProxy(
            token=_TOKEN,  # type: ignore[arg-type]
            allowlist=frozenset({_CHANNEL}),  # type: ignore[arg-type]
            enable_writes=False,  # read-only: never posts to the workspace
        )
        result = proxy.execute(_event("access_confidential_channel", _CHANNEL))  # type: ignore[arg-type]
        self.assertTrue(result.ok, result.error)
        self.assertIsNotNone(result.side_effect_hash)
        self.assertTrue(result.response.get("ok"))


if __name__ == "__main__":
    unittest.main()
