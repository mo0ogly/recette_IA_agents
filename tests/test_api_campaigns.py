"""Campaign + recording + replay routes over HTTP (discovery recette)."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app
    from recette.api.campaign_store import CampaignStore, RecordingStore
    from recette.api.config_store import ConfigStore

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover
    _HAS_FASTAPI = False


def _wait_terminal(client, run_id, tries=300):
    for _ in range(tries):
        body = client.get(f"/runs/{run_id}").json()
        if body["status"] in {"completed", "failed", "stopped"}:
            return body
        time.sleep(0.01)
    raise AssertionError("run did not terminate")


_STUB = [
    {"kind": "tool_call", "tool_name": "read_repo", "tool_args": {"resource": "acme/x"}},
    {"kind": "tool_call", "tool_name": "open_pr", "tool_args": {"resource": "acme/x"}},
    {"kind": "final", "text": "done"},
]


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class TestCampaignRoutes(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        config = ConfigStore(root / "config.json")
        config.add_agent(
            {
                "id": "gh-pr-bot",
                "runtime": "lab",
                "principal": "bot@acme",
                "target_system": "github",
                "goal": "open a PR",
                "capability_scope": ["read_repo", "open_pr"],
            }
        )
        self.client = TestClient(
            create_app(
                config_store=config,
                campaign_store=CampaignStore(root / "campaigns.json"),
                recording_store=RecordingStore(root / "recordings"),
            )
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_create_run_then_replay_is_deterministic(self) -> None:
        # Create a one-step mock campaign.
        created = self.client.post(
            "/campaigns",
            json={
                "id": "camp-pr",
                "description": "PR bot",
                "steps": [{"agent_id": "gh-pr-bot", "stub_script": _STUB}],
            },
        )
        self.assertEqual(created.status_code, 201)
        self.assertIn("camp-pr", [c["id"] for c in self.client.get("/campaigns").json()["campaigns"]])

        # Run it; one recording is persisted.
        run_id = self.client.post("/campaigns/camp-pr/run").json()["run_id"]
        self.assertEqual(_wait_terminal(self.client, run_id)["status"], "completed")
        recs = self.client.get("/recordings").json()["recordings"]
        self.assertEqual(len(recs), 1)
        rec_id = recs[0]["recording_id"]

        # Replay reproduces the exact action log (I4).
        replay_id = self.client.post(f"/recordings/{rec_id}/replay").json()["run_id"]
        self.assertEqual(_wait_terminal(self.client, replay_id)["status"], "completed")
        events = self.client.get(f"/runs/{replay_id}/events").json()
        result = next(e for e in events if e["type"] == "replay_result")
        self.assertTrue(result["data"]["matches_original"])

    def test_run_unknown_campaign_404(self) -> None:
        self.assertEqual(self.client.post("/campaigns/nope/run").status_code, 404)

    def test_create_duplicate_400(self) -> None:
        body = {"id": "dup", "description": "", "steps": [{"agent_id": "gh-pr-bot", "stub_script": _STUB}]}
        self.assertEqual(self.client.post("/campaigns", json=body).status_code, 201)
        self.assertEqual(self.client.post("/campaigns", json=body).status_code, 400)

    def test_replay_unknown_recording_404(self) -> None:
        self.assertEqual(self.client.post("/recordings/nope/replay").status_code, 404)
