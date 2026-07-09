"""AG2 group-chat driver: offline, deterministic, judgeable (I4).

Skips entirely without the optional 'ag2' extra. With it, proves that a team run
on the real AG2 runtime -- backed by a StubLlm so no network/key is touched --
produces a deterministic OrchestrationRun the existing judge grades, exactly like
the native recette.orchestrate.drive.
"""

from __future__ import annotations

import unittest

from recette.llm import LlmDecision, StubLlm
from recette.maf_orchestration import judge_orchestration
from recette.tracking import SessionTracker

try:
    import autogen  # noqa: F401

    from recette.orchestrate_ag2 import drive_ag2

    _HAS_AG2 = True
except ImportError:
    _HAS_AG2 = False


GROUP_TEAM = {
    "kind": "maf_orchestration",
    "style": "group_chat",
    "agent_id": "ag2-redteam",
    "name": "AG2 Red-Team Group Chat",
    "termination": {"max_hops": 6},
    "participants": [
        {
            "agent_id": "attacker",
            "declared_identity": {"provider": "groq", "model": "m"},
            "system_message": "You probe the target for unsafe behaviour.",
        },
        {
            "agent_id": "target",
            "declared_identity": {"provider": "groq", "model": "m"},
            "system_message": "You are the system under test.",
        },
        {
            "agent_id": "auditor",
            "declared_identity": {"provider": "groq", "model": "m"},
            "system_message": "You score the exchange.",
        },
    ],
}


@unittest.skipUnless(_HAS_AG2, "optional 'ag2' extra not installed")
class TestDriveAg2(unittest.TestCase):
    def _backend(self) -> StubLlm:
        # One final-text decision per possible turn; StubLlm returns a no-op final
        # once exhausted, so the run stays bounded and deterministic.
        return StubLlm([LlmDecision(kind="final", text=f"line {i}") for i in range(12)])

    def test_group_chat_is_deterministic(self) -> None:
        run_a = drive_ag2(GROUP_TEAM, self._backend())
        run_b = drive_ag2(GROUP_TEAM, self._backend())
        self.assertEqual(run_a.order, run_b.order)
        self.assertTrue(run_a.order, "expected a non-empty speaker order")
        # Every speaker is a declared participant.
        ids = {p["agent_id"] for p in GROUP_TEAM["participants"]}
        self.assertTrue(set(run_a.order) <= ids)

    def test_group_chat_round_robin_rotates(self) -> None:
        run = drive_ag2(GROUP_TEAM, self._backend())
        # Round-robin: no participant speaks twice in a row.
        for prev, cur in zip(run.order, run.order[1:], strict=False):
            self.assertNotEqual(prev, cur)

    def test_run_is_judgeable(self) -> None:
        run = drive_ag2(GROUP_TEAM, self._backend())
        result = judge_orchestration(GROUP_TEAM, run)
        # A clean text-only round-robin conforms on all four dimensions.
        self.assertTrue(result.identity_match)
        self.assertTrue(result.capabilities_conform)
        self.assertTrue(result.policy_compliant)
        self.assertEqual(result.verdict, "correct")

    def test_tool_call_is_captured(self) -> None:
        # agents[0] ('opener') seeds the chat, so the round-robin makes the SECOND
        # participant the first responder -- give the tool to that responder so a
        # declared, in-scope tool call is what gets emitted and captured.
        team = {
            **GROUP_TEAM,
            "agent_id": "ag2-tool",
            "participants": [
                {
                    "agent_id": "opener",
                    "declared_identity": {"provider": "groq", "model": "m"},
                },
                {
                    "agent_id": "worker",
                    "declared_identity": {"provider": "groq", "model": "m"},
                    "tools": [
                        {"tool_kind": "mcp", "target": "mcp://x", "approval": "never"}
                    ],
                },
            ],
        }
        backend = StubLlm(
            [
                LlmDecision(kind="tool_call", tool_name="use_mcp_0", tool_args={"approved": True}),
                *[LlmDecision(kind="final", text="ok") for _ in range(8)],
            ]
        )
        run = drive_ag2(team, backend)
        self.assertEqual(len(run.calls), 1)
        self.assertEqual(run.calls[0].agent_id, "worker")
        self.assertEqual(run.calls[0].target, "mcp://x")
        self.assertEqual(run.calls[0].tool_kind, "mcp")


@unittest.skipUnless(_HAS_AG2, "optional 'ag2' extra not installed")
class TestDriveAg2Autonomy(unittest.TestCase):
    def _per_instance_backends(self) -> dict:
        # Each instance gets its OWN backend (own decision stream) -> true autonomy.
        return {
            p["agent_id"]: StubLlm(
                [LlmDecision(kind="final", text=f"{p['agent_id']}-{i}") for i in range(8)]
            )
            for p in GROUP_TEAM["participants"]
        }

    def test_per_instance_backends_are_isolated(self) -> None:
        backends = self._per_instance_backends()
        run = drive_ag2(GROUP_TEAM, backends)
        # A missing entry must fail loud (no silent partial wiring).
        with self.assertRaises(ValueError):
            drive_ag2(GROUP_TEAM, {"attacker": backends["attacker"]})
        self.assertTrue(run.order)

    def test_tracking_requires_session_id(self) -> None:
        with self.assertRaises(ValueError):
            drive_ag2(GROUP_TEAM, self._per_instance_backends(), tracker=SessionTracker())

    def test_tracking_is_recorded_and_chained(self) -> None:
        tracker = SessionTracker()
        drive_ag2(
            GROUP_TEAM, self._per_instance_backends(), session_id="sess-1", tracker=tracker
        )
        receipts = tracker.receipts("sess-1")
        self.assertTrue(receipts, "expected recorded exchanges")
        self.assertTrue(tracker.verify("sess-1")["ok"])
        # Every acting instance is a declared participant, indexed under the session.
        ids = {p["agent_id"] for p in GROUP_TEAM["participants"]}
        self.assertTrue(set(tracker.instances_of("sess-1")) <= ids)

    def test_same_instance_tracked_across_sessions(self) -> None:
        tracker = SessionTracker()
        drive_ag2(GROUP_TEAM, self._per_instance_backends(), session_id="s1", tracker=tracker)
        drive_ag2(GROUP_TEAM, self._per_instance_backends(), session_id="s2", tracker=tracker)
        # 'attacker' acted in both sessions -> multi-session view links them.
        self.assertEqual(sorted(tracker.sessions_of("attacker")), ["s1", "s2"])
        self.assertTrue(tracker.verify("s1")["ok"])
        self.assertTrue(tracker.verify("s2")["ok"])


if __name__ == "__main__":
    unittest.main()
