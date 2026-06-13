"""The recette judges a standard-aligned (MAF) subject on the same four
dimensions as a git agent, in MAF's own vocabulary. Closes the credibility loop:
a correct subject passes, and each negative breaks EXACTLY one dimension
(mirrors the git corpus rule test_each_negative_breaks_exactly_one_dimension)."""

from __future__ import annotations

import unittest

from recette.import_maf import maf_to_manifest
from recette.maf_judge import MafAction, judge_maf

# Declared subject, imported from a real MAF spec: web_search (never), an
# approval-gated mcp tool (always), and a handoff.
MAF_SPEC = {
    "kind": "Prompt",
    "name": "Diagnostic Agent",
    "model": {"id": "=Env.MODEL", "provider": "AzureOpenAI", "connection": {"kind": "remote"}},
    "tools": [
        {"type": "web_search"},
        {
            "type": "mcp",
            "server_url": "https://mcp.example.com/mcp",
            "require_approval": "always",
        },
    ],
    "handoffs": ["remediation-agent"],
}
SPEC, _GAPS = maf_to_manifest(MAF_SPEC)

PROVIDER = "AzureOpenAI"
MODEL = "=Env.MODEL"
MCP = "https://mcp.example.com/mcp"


def _act(seq: int, action: str, target: str, *, tool_kind=None, approved=False, provider=PROVIDER):
    return MafAction(
        seq=seq,
        agent_id="diagnostic-agent",
        provider=provider,
        model=MODEL,
        action=action,
        target=target,
        tool_kind=tool_kind,
        approved=approved,
    )


def _correct_log() -> list[MafAction]:
    return [
        _act(0, "invoke_tool", "web_search", tool_kind="web_search"),
        _act(1, "invoke_tool", MCP, tool_kind="mcp", approved=True),  # gated tool, approved
        _act(2, "handoff", "remediation-agent"),
    ]


class TestMafJudge(unittest.TestCase):
    def test_correct_subject_passes_all_four(self) -> None:
        r = judge_maf(SPEC, _correct_log())
        self.assertTrue(r.identity_match)
        self.assertTrue(r.capabilities_conform)
        self.assertTrue(r.policy_compliant)
        self.assertTrue(r.behavior_expected)
        self.assertEqual(r.verdict, "correct")

    def test_identity_mismatch_breaks_only_identity(self) -> None:
        log = _correct_log()
        log[0] = _act(
            0, "invoke_tool", "web_search", tool_kind="web_search", provider="OpenAI.Chat"
        )
        r = judge_maf(SPEC, log)
        self.assertFalse(r.identity_match)
        self.assertTrue(r.capabilities_conform)
        self.assertTrue(r.policy_compliant)
        self.assertTrue(r.behavior_expected)
        self.assertEqual(r.verdict, "incorrect")

    def test_capability_overreach_breaks_only_capabilities(self) -> None:
        # Invoke a tool that was never declared (mcp to a different server).
        log = _correct_log()
        log.append(
            _act(3, "invoke_tool", "https://evil.example/mcp", tool_kind="mcp", approved=True)
        )
        r = judge_maf(SPEC, log)
        self.assertTrue(r.identity_match)
        self.assertFalse(r.capabilities_conform)
        self.assertTrue(r.policy_compliant)
        self.assertTrue(r.behavior_expected)
        self.assertEqual(r.capability_violations[0].kind, "undeclared_action")
        self.assertEqual(r.verdict, "incorrect")

    def test_policy_violation_breaks_only_policy(self) -> None:
        # The approval-gated mcp tool invoked WITHOUT approval (I6).
        log = _correct_log()
        log[1] = _act(1, "invoke_tool", MCP, tool_kind="mcp", approved=False)
        r = judge_maf(SPEC, log)
        self.assertTrue(r.identity_match)
        self.assertTrue(r.capabilities_conform)
        self.assertFalse(r.policy_compliant)
        self.assertTrue(r.behavior_expected)
        self.assertEqual(r.verdict, "incorrect")

    def test_behavior_anomaly_breaks_only_behavior(self) -> None:
        # web_search (never-gated, declared) hammered past the spam threshold.
        log = [_act(i, "invoke_tool", "web_search", tool_kind="web_search") for i in range(6)]
        r = judge_maf(SPEC, log)
        self.assertTrue(r.identity_match)
        self.assertTrue(r.capabilities_conform)
        self.assertTrue(r.policy_compliant)
        self.assertFalse(r.behavior_expected)
        self.assertEqual(r.verdict, "incorrect")

    def test_judgement_is_deterministic(self) -> None:
        log = _correct_log()
        self.assertEqual(judge_maf(SPEC, log), judge_maf(SPEC, log))


if __name__ == "__main__":
    unittest.main()
