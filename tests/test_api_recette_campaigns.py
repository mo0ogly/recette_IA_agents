# tests/test_api_recette_campaigns.py
"""Read-only catalog of on-disk recette governance campaigns (campaigns/**).

Distinct from the CRUD campaign store: these carry {name, objective, teaching,
agents, actions(+expect)} and are exposed read-only so the console can list and
explain them. The catalog reuses recette.campaign.load_campaign for validation
(no parallel parser); an invalid file is surfaced, never fatal."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from recette.api.recette_campaigns import RecetteCampaignCatalog

try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover
    _HAS_FASTAPI = False

_CAMPAIGN = {
    "name": "demo-fraud",
    "objective": "prove a wire fraud is escalated",
    "teaching": "redirecting a payee must require approval",
    "agents": [{"id": "a1", "runtime": "lab"}],
    "actions": [
        {
            "agent_id": "a1",
            "target_system": "finance",
            "action_type": "launch_wire_transfer",
            "resource": "payment/1",
            "expect": "escalate",
            "rationale": "high blast radius",
        }
    ],
}


class TestRecetteCampaignCatalog(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        (root / "banque").mkdir()
        (root / "banque" / "demo.campaign.json").write_text(json.dumps(_CAMPAIGN), encoding="utf-8")
        # An invalid file must be surfaced, not crash the listing.
        (root / "broken.campaign.json").write_text("{ not json", encoding="utf-8")
        self.catalog = RecetteCampaignCatalog(root)

    def test_list_includes_valid_summary_and_marks_invalid(self) -> None:
        items = self.catalog.list()
        self.assertEqual(len(items), 2)
        valid = next(c for c in items if c["id"] == "demo-fraud")
        self.assertEqual(valid["family"], "banque")
        self.assertEqual(valid["action_count"], 1)
        self.assertEqual(valid["agent_count"], 1)
        self.assertEqual(valid["objective"], "prove a wire fraud is escalated")
        broken = next(c for c in items if "error" in c)
        self.assertIn("error", broken)

    def test_get_returns_full_document_with_family(self) -> None:
        doc = self.catalog.get("demo-fraud")
        self.assertIsNotNone(doc)
        assert doc is not None
        self.assertEqual(doc["family"], "banque")
        self.assertEqual(doc["actions"][0]["expect"], "escalate")

    def test_get_unknown_is_none(self) -> None:
        self.assertIsNone(self.catalog.get("nope"))

    def test_macro_orchestration_campaign_is_linked(self) -> None:
        """A campaign with a 'links' block is flagged linked in the summary and
        its links survive in the detail (macro orchestration campaign)."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "multidomain").mkdir()
        doc = {
            **_CAMPAIGN,
            "name": "linked-demo",
            "links": [
                {
                    "kind": "maf_orchestration",
                    "team": "finance-approval-handoff-correct",
                    "shared_action": "launch_wire_transfer",
                    "invariant": "I6",
                }
            ],
        }
        (root / "multidomain" / "linked.campaign.json").write_text(
            json.dumps(doc), encoding="utf-8"
        )
        catalog = RecetteCampaignCatalog(root)
        summary = next(c for c in catalog.list() if c["id"] == "linked-demo")
        self.assertTrue(summary["linked"])
        detail = catalog.get("linked-demo")
        assert detail is not None
        self.assertEqual(detail["links"][0]["team"], "finance-approval-handoff-correct")

    def test_plain_campaign_not_linked(self) -> None:
        summary = next(c for c in self.catalog.list() if c["id"] == "demo-fraud")
        self.assertFalse(summary["linked"])


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class TestRecetteCampaignRoutes(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        (root / "rag").mkdir()
        (root / "rag" / "demo.campaign.json").write_text(json.dumps(_CAMPAIGN), encoding="utf-8")
        self.client = TestClient(create_app(recette_campaign_catalog=RecetteCampaignCatalog(root)))

    def test_list_route(self) -> None:
        body = self.client.get("/recette-campaigns").json()
        self.assertEqual(len(body["campaigns"]), 1)
        self.assertEqual(body["campaigns"][0]["family"], "rag")

    def test_detail_route(self) -> None:
        body = self.client.get("/recette-campaigns/demo-fraud").json()
        self.assertEqual(body["actions"][0]["action_type"], "launch_wire_transfer")

    def test_unknown_detail_404(self) -> None:
        self.assertEqual(self.client.get("/recette-campaigns/nope").status_code, 404)


if __name__ == "__main__":
    unittest.main()
