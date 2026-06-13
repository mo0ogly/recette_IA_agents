"""Recette of the operator knowledge-base store + scenarios + reset.

Guards the lifecycle the RAG poisoning recette depends on: CRUD, deterministic
reset to the clean baseline (I4), named scenario injection, the lab handler
reflecting the live store (so a live agent query sees the applied poison), and
the I2-safety boundary (the store is off the agent path).
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from recette.lab.domains import knowledge_base as kb_lab
from recette.rag_store import KnowledgeBaseError, KnowledgeBaseStore

REPO = Path(__file__).resolve().parent.parent
SCENARIOS = REPO / "corpus" / "rag" / "scenarios"

_DOC = {
    "id": "test-doc-1",
    "title": "Test document",
    "content": "hello world",
    "poisoned": False,
    "tags": ["test"],
}


class TestKnowledgeBaseStore(unittest.TestCase):
    def setUp(self) -> None:
        self.store = KnowledgeBaseStore()
        self.store.reset()  # isolate the shared in-memory state per test

    def test_documents_lists_baseline(self) -> None:
        ids = {d["id"] for d in self.store.documents()}
        self.assertIn("kb-onboarding-1", ids)

    def test_add_get_delete(self) -> None:
        self.store.add(dict(_DOC))
        self.assertIsNotNone(self.store.get("test-doc-1"))
        self.store.delete("test-doc-1")
        self.assertIsNone(self.store.get("test-doc-1"))

    def test_add_rejects_duplicate_id(self) -> None:
        self.store.add(dict(_DOC))
        with self.assertRaises(KnowledgeBaseError):
            self.store.add(dict(_DOC))

    def test_add_validates_poison_fields(self) -> None:
        bad = {"id": "p1", "title": "t", "content": "c", "poisoned": True, "tags": []}
        with self.assertRaises(KnowledgeBaseError):
            self.store.add(bad)

    def test_delete_unknown_raises(self) -> None:
        with self.assertRaises(KnowledgeBaseError):
            self.store.delete("nope")

    def test_reset_is_deterministic(self) -> None:
        baseline = [d["id"] for d in self.store.documents()]
        self.store.add(dict(_DOC))
        self.store.apply_scenario("exfil-finance")
        self.store.reset()
        self.assertEqual([d["id"] for d in self.store.documents()], baseline)

    def test_apply_scenario_injects_poison(self) -> None:
        injected = self.store.apply_scenario("exfil-finance")
        self.assertEqual([d["id"] for d in injected], ["scn-exfil-finance"])
        self.assertIsNotNone(self.store.get("scn-exfil-finance"))

    def test_apply_unknown_scenario_raises(self) -> None:
        with self.assertRaises(KnowledgeBaseError):
            self.store.apply_scenario("does-not-exist")

    def test_lab_handler_reflects_store(self) -> None:
        # Before: baseline finance docs, no scenario poison.
        before = kb_lab.handle("query_knowledge_base", "quarterly", {})
        assert before is not None
        self.assertFalse(any(d["id"] == "scn-exfil-finance" for d in before["documents"]))
        # Apply the scenario: a live query must now surface the injected poison.
        self.store.apply_scenario("exfil-finance")
        after = kb_lab.handle("query_knowledge_base", "quarterly", {})
        assert after is not None
        self.assertTrue(any(d["id"] == "scn-exfil-finance" for d in after["documents"]))
        # Reset un-poisons.
        self.store.reset()
        clean = kb_lab.handle("query_knowledge_base", "quarterly", {})
        assert clean is not None
        self.assertFalse(any(d["id"] == "scn-exfil-finance" for d in clean["documents"]))


class TestRagScenarios(unittest.TestCase):
    def test_scenarios_are_well_formed(self) -> None:
        scenario_files = [p for p in SCENARIOS.glob("*.json") if p.name != "scenario.schema.json"]
        self.assertTrue(scenario_files, "no scenario files found")
        for path in scenario_files:
            spec = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(spec["name"], path.stem)
            for doc in spec["documents"]:
                if doc["poisoned"]:
                    # A poison scenario must declare an induced action that is
                    # blocked: deny or escalate, never a silent allow.
                    self.assertIn(doc["injected_expect"], {"deny", "escalate"}, path.name)
                    for key in ("injected_action", "injected_target_system", "threat"):
                        self.assertIn(key, doc, f"{path.name}:{doc['id']} missing {key}")


if __name__ == "__main__":
    unittest.main()
