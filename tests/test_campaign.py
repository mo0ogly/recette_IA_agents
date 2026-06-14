"""Campaign runner: validation, governed submission, expectation checking."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from recette.campaign import (
    CampaignError,
    CampaignRunner,
    load_campaign,
    validate_campaign,
)

try:
    from fastapi.testclient import TestClient

    HAVE_FASTAPI = True
except ImportError:  # pragma: no cover - dev venv always has fastapi
    HAVE_FASTAPI = False

CAMPAIGNS_DIR = Path(__file__).resolve().parents[1] / "campaigns"


class TestCampaignValidation(unittest.TestCase):
    def test_committed_campaign_files_are_valid(self) -> None:
        # Recursive: the catalog (RecetteCampaignCatalog) reads campaigns/** with
        # rglob, so this validity gate must too -- otherwise the multidomain/, bnp/,
        # coverage/, rag/ subdirs ship unvalidated.
        files = sorted(CAMPAIGNS_DIR.rglob("*.campaign.json"))
        self.assertGreaterEqual(len(files), 3)
        for path in files:
            doc = load_campaign(path)  # raises on invalid
            self.assertTrue(doc["name"])

    def test_rejects_missing_actions(self) -> None:
        with self.assertRaises(CampaignError):
            validate_campaign({"name": "x", "agents": [], "actions": []})

    def test_rejects_bad_expect(self) -> None:
        with self.assertRaises(CampaignError):
            validate_campaign(
                {
                    "name": "x",
                    "agents": [],
                    "actions": [
                        {
                            "agent_id": "a",
                            "target_system": "okta",
                            "action_type": "suspend_user",
                            "resource": "r",
                            "expect": "maybe",
                        }
                    ],
                }
            )

    def _doc_with_links(self, links: object) -> dict:
        return {
            "name": "x",
            "links": links,
            "agents": [{"id": "a", "runtime": "lab"}],
            "actions": [
                {
                    "agent_id": "a",
                    "target_system": "finance",
                    "action_type": "launch_wire_transfer",
                    "resource": "r",
                    "expect": "escalate",
                }
            ],
        }

    def test_accepts_valid_maf_link(self) -> None:
        validate_campaign(
            self._doc_with_links(
                [
                    {
                        "kind": "maf_orchestration",
                        "team": "finance-approval-handoff-correct",
                        "shared_action": "launch_wire_transfer",
                        "invariant": "I6",
                    }
                ]
            )
        )

    def test_rejects_link_missing_team(self) -> None:
        with self.assertRaises(CampaignError):
            validate_campaign(
                self._doc_with_links(
                    [{"kind": "maf_orchestration", "shared_action": "launch_wire_transfer"}]
                )
            )

    def test_rejects_link_unknown_kind(self) -> None:
        with self.assertRaises(CampaignError):
            validate_campaign(
                self._doc_with_links(
                    [{"kind": "lane_b", "team": "t", "shared_action": "launch_wire_transfer"}]
                )
            )


@unittest.skipUnless(HAVE_FASTAPI, "fastapi not installed")
class TestCampaignRunner(unittest.TestCase):
    """Runs a campaign in-process against the real app (stub proxy)."""

    def setUp(self) -> None:
        from recette.api.app import create_app
        from recette.api.config_store import ConfigStore
        from recette.platform.catalog import load_catalog
        from recette.platform.eventstore.memory_store import InMemoryEventStore
        from recette.platform.policy.store import PolicyStore
        from recette.platform.proxy.protocol import ExecutionResult, side_effect_hash

        class StubProxy:
            def execute(self, event):  # type: ignore[no-untyped-def]
                response = {"done": True}
                return ExecutionResult(
                    ok=True,
                    status_code=200,
                    response=response,
                    side_effect_hash=side_effect_hash(
                        event.target_system, event.action_type, event.resource, response
                    ),
                )

        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        app = create_app(
            config_store=ConfigStore(tmp / "config.json"),
            event_store=InMemoryEventStore(),
            policy_store=PolicyStore(tmp / "policies"),
            proxy=StubProxy(),
            catalog=load_catalog(),
        )
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_redteam_probe_all_denied_and_chain_intact(self) -> None:
        doc = load_campaign(CAMPAIGNS_DIR / "redteam-probe.campaign.json")
        report = CampaignRunner(self.client).run(doc)
        self.assertTrue(report.ok)
        self.assertEqual(report.counts["deny"], len(doc["actions"]))
        self.assertEqual(report.pending_event_ids, [])
        self.assertTrue(report.chain_ok)

    def test_identity_offboarding_escalates_and_pends(self) -> None:
        doc = load_campaign(CAMPAIGNS_DIR / "identity-offboarding.campaign.json")
        report = CampaignRunner(self.client).run(doc)
        self.assertTrue(report.ok)
        self.assertEqual(report.counts["escalate"], 3)
        self.assertEqual(report.counts["deny"], 1)  # disable_sso pure-DENY row
        self.assertEqual(len(report.pending_event_ids), 3)
        # I6: nothing executed while pending.
        self.assertTrue(all(not r.executed for r in report.results))

    def test_expectation_mismatch_fails_the_report(self) -> None:
        doc = {
            "name": "mismatch",
            "agents": [
                {"id": "camp-x", "runtime": "lab", "role": "marketing_bot"},
            ],
            "actions": [
                {
                    "agent_id": "camp-x",
                    "target_system": "okta",
                    "action_type": "suspend_user",
                    "resource": "user/x",
                    "expect": "allow",  # reality: deny for an unprivileged role
                }
            ],
        }
        report = CampaignRunner(self.client).run(doc)
        self.assertFalse(report.ok)
        self.assertEqual(len(report.mismatches), 1)
        payload = json.dumps(report.to_dict())
        self.assertIn('"mismatch_count": 1', payload)

    def test_rerun_tolerates_existing_agents(self) -> None:
        doc = load_campaign(CAMPAIGNS_DIR / "redteam-probe.campaign.json")
        runner = CampaignRunner(self.client)
        first = runner.run(doc)
        second = runner.run(doc)  # agents already seeded -> 400 tolerated
        self.assertTrue(first.ok)
        self.assertTrue(second.ok)


if __name__ == "__main__":
    unittest.main()
