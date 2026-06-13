"""The unified judge_subject routes each family to the right four-dimension
evaluator: a maf_agent manifest goes to the MAF judge, a git agent manifest goes
to the reference git adapter -- one entrypoint, one IdentificationResult contract."""

from __future__ import annotations

import unittest

from recette.events import AgentAction
from recette.import_maf import maf_to_manifest
from recette.judge import judge_subject, subject_family
from recette.maf_judge import MafAction

MAF_SPEC = {
    "kind": "Prompt",
    "name": "Diagnostic Agent",
    "model": {"id": "=Env.MODEL", "provider": "AzureOpenAI", "connection": {"kind": "remote"}},
    "tools": [{"type": "web_search"}],
    "handoffs": ["remediation-agent"],
}

GIT_MANIFEST = {
    "agent_id": "pr-bot",
    "name": "PR Bot",
    "target_systems": ["github"],
    "declared_identity": {"auth_method": "github_app", "principal": "pr-bot[bot]"},
    "capability_scope": [{"action": "open_pr", "mode": "write", "resources": ["acme/*"]}],
    "runtime": {"lab_mode": True, "real_mode": False},
    "version": "0.1.0",
}


class TestUnifiedJudge(unittest.TestCase):
    def test_family_discriminator(self) -> None:
        self.assertEqual(subject_family(GIT_MANIFEST), "git_agent")  # default
        self.assertEqual(subject_family({"kind": "maf_agent"}), "maf_agent")

    def test_routes_maf_subject(self) -> None:
        spec, _ = maf_to_manifest(MAF_SPEC)
        log = [
            MafAction(
                0,
                spec["agent_id"],
                "AzureOpenAI",
                "=Env.MODEL",
                "invoke_tool",
                "web_search",
                tool_kind="web_search",
            ),
            MafAction(
                1, spec["agent_id"], "AzureOpenAI", "=Env.MODEL", "handoff", "remediation-agent"
            ),
        ]
        r = judge_subject(spec, log)
        self.assertEqual(r.verdict, "correct")

    def test_routes_git_subject(self) -> None:
        log = [
            AgentAction(
                event_id="e0",
                seq=0,
                timestamp="t",
                agent_id="pr-bot",
                principal="pr-bot[bot]",
                target_system="github",
                action_type="open_pr",
                mode="write",
                resource="acme/widgets",
                approved=False,
            )
        ]
        r = judge_subject(GIT_MANIFEST, log)
        self.assertEqual(r.verdict, "correct")


if __name__ == "__main__":
    unittest.main()
