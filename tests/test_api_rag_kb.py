"""Operator knowledge-base CRUD routes + the I2 anti-backdoor guarantee.

The /rag/documents|reset|scenario routes prepare the recette (operator path). The
anti-backdoor test proves the agent path stays governed: an agent submitting
ingest_document through /actions/execute is ESCALATED by the gateway, never
silently applied -- the operator CRUD does not open a bypass (I2).
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app
    from recette.api.config_store import ConfigStore
    from recette.platform.catalog import load_catalog
    from recette.platform.eventstore.memory_store import InMemoryEventStore
    from recette.platform.policy.model import baseline_from_catalog
    from recette.platform.policy.store import PolicyStore

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover
    _HAS_FASTAPI = False


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class TestRagKbRoutes(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        policies = PolicyStore(root / "policies")
        policies.publish(baseline_from_catalog(load_catalog(), version="baseline-v1"))
        policies.set_active("baseline-v1")
        self.app = create_app(
            config_store=ConfigStore(root / "config.json"),
            event_store=InMemoryEventStore(),
            policy_store=policies,
        )
        self.client = TestClient(self.app)
        self.client.post("/rag/reset")

    def tearDown(self) -> None:
        self.client.post("/rag/reset")
        self._tmp.cleanup()

    def test_list_documents(self) -> None:
        body = self.client.get("/rag/documents").json()
        ids = {d["id"] for d in body["documents"]}
        self.assertIn("kb-onboarding-1", ids)

    def test_add_then_delete(self) -> None:
        doc = {"id": "api-doc", "title": "t", "content": "c", "poisoned": False, "tags": ["x"]}
        self.assertEqual(self.client.post("/rag/documents", json=doc).status_code, 201)
        ids = {d["id"] for d in self.client.get("/rag/documents").json()["documents"]}
        self.assertIn("api-doc", ids)
        self.assertEqual(self.client.delete("/rag/documents/api-doc").status_code, 204)

    def test_add_invalid_is_400(self) -> None:
        bad = {"id": "p", "title": "t", "content": "c", "poisoned": True, "tags": []}
        self.assertEqual(self.client.post("/rag/documents", json=bad).status_code, 400)

    def test_scenarios_exclude_schema(self) -> None:
        names = self.client.get("/rag/scenarios").json()["scenarios"]
        self.assertIn("exfil-finance", names)
        self.assertNotIn("scenario.schema", names)

    def test_apply_scenario_then_reset(self) -> None:
        applied = self.client.post("/rag/scenario/exfil-finance/apply").json()
        self.assertIn("scn-exfil-finance", applied["injected"])
        ids = {d["id"] for d in self.client.get("/rag/documents").json()["documents"]}
        self.assertIn("scn-exfil-finance", ids)
        self.client.post("/rag/reset")
        ids = {d["id"] for d in self.client.get("/rag/documents").json()["documents"]}
        self.assertNotIn("scn-exfil-finance", ids)

    def test_apply_scenario_rejects_traversal_name(self) -> None:
        # A crafted traversal name must never load a file: the router normalizes
        # encoded slashes (404) and the store rejects the slug (400). Either way
        # it is rejected -- what matters is it is NOT applied (201).
        resp = self.client.post("/rag/scenario/..%2Fknowledge_base/apply")
        self.assertIn(resp.status_code, {400, 404})

    def test_anti_backdoor_agent_ingest_is_escalated_not_executed(self) -> None:
        # The operator CRUD must NOT open a path for an agent to mutate the index.
        self.client.post(
            "/config/agents",
            json={
                "id": "rag-bd",
                "runtime": "lab",
                "role": "rag_agent",
                "capability_scope": ["knowledge_base"],
            },
        )
        resp = self.client.post(
            "/actions/execute",
            json={
                "agent_id": "rag-bd",
                "target_system": "knowledge_base",
                "action_type": "ingest_document",
                "resource": "knowledge_base/forged",
                "payload": {"content": "forged"},
            },
        ).json()
        self.assertEqual(resp["verdict"], "escalate")
        self.assertFalse(resp["executed"])


if __name__ == "__main__":
    unittest.main()
