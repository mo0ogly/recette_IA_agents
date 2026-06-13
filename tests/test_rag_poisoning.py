"""RAG poisoning recette: a polluted knowledge base cannot bypass the gateway.

Asserts, against the pure policy decision function (no HTTP, deterministic I4):
  - every action of every campaigns/rag/ campaign decides to its expected verdict;
  - the KB-guard: every poisoned document in corpus/rag/knowledge_base.json is
    exercised by a rag campaign whose induced action and verdict match the doc's
    injected_action / injected_expect (so a new poisoned doc with no campaign, or
    a campaign drifting from the doc, fails the suite);
  - poison only ever induces deny/escalate actions, never a silent allow.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from recette.platform.catalog import Catalog, load_catalog
from recette.platform.catalog.model import RISK_SCORE, RiskLevel
from recette.platform.events import PlatformActionEvent
from recette.platform.policy.engine import decide
from recette.platform.policy.model import PolicyVersion, baseline_from_catalog

REPO = Path(__file__).resolve().parent.parent
RAG_CAMPAIGNS = REPO / "campaigns" / "rag"
KB_SEED = REPO / "corpus" / "rag" / "knowledge_base.json"


def _event(role: str, target_system: str, action_type: str) -> PlatformActionEvent:
    return PlatformActionEvent(
        event_id="ev-test",
        timestamp="2023-11-14T22:13:20Z",
        agent_id="rag-test",
        capability_scope=("knowledge_base",),
        role=role,
        action_type=action_type,
        target_system=target_system,
        resource="x",
        payload={},
        risk_score=RISK_SCORE[RiskLevel.LOW],
        risk_level=RiskLevel.LOW,
    )


class TestRagPoisoning(unittest.TestCase):
    catalog: Catalog
    policy: PolicyVersion
    campaigns: list[dict]
    kb: list[dict]

    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_catalog()
        cls.policy = baseline_from_catalog(cls.catalog, version="baseline-v1")
        cls.campaigns = [
            json.loads(p.read_text(encoding="utf-8")) for p in sorted(RAG_CAMPAIGNS.glob("*.json"))
        ]
        cls.kb = json.loads(KB_SEED.read_text(encoding="utf-8"))["documents"]

    def test_every_rag_action_decides_to_expected_verdict(self) -> None:
        for doc in self.campaigns:
            role = doc["agents"][0]["role"]
            for action in doc["actions"]:
                event = _event(role, action["target_system"], action["action_type"])
                verdict = str(decide(event, self.policy, self.catalog).verdict)
                self.assertEqual(
                    verdict,
                    action["expect"],
                    f"{doc['name']}: {action['action_type']} expected {action['expect']}, "
                    f"engine said {verdict}",
                )

    def test_kb_guard_every_poisoned_doc_has_a_campaign(self) -> None:
        induced = {
            (a["target_system"], a["action_type"], a["expect"])
            for doc in self.campaigns
            for a in doc["actions"]
        }
        for kb_doc in self.kb:
            if not kb_doc.get("poisoned"):
                continue
            key = (
                kb_doc["injected_target_system"],
                kb_doc["injected_action"],
                kb_doc["injected_expect"],
            )
            self.assertIn(
                key,
                induced,
                f"poisoned doc {kb_doc['id']} injects {key} but no rag campaign exercises it",
            )

    def test_poison_only_induces_deny_or_escalate(self) -> None:
        # In a poisoned campaign every non-retrieval action (the induced one) must
        # be blocked: deny or escalate, never allow.
        for doc in self.campaigns:
            if "poisoned" not in doc["name"]:
                continue
            for action in doc["actions"]:
                if action["action_type"] == "query_knowledge_base":
                    continue
                self.assertIn(
                    action["expect"],
                    {"deny", "escalate"},
                    f"{doc['name']}: induced {action['action_type']} must be blocked",
                )

    def test_at_least_one_clean_and_each_threat_covered(self) -> None:
        names = {doc["name"] for doc in self.campaigns}
        self.assertIn("rag-clean", names)
        threats = {kb["threat"] for kb in self.kb if kb.get("poisoned")}
        self.assertEqual(threats, {"exfiltration", "invalid_command", "invalid_data"})


if __name__ == "__main__":
    unittest.main()
