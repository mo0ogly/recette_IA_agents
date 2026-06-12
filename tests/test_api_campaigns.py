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
        self.config = config = ConfigStore(root / "config.json")
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
        campaigns = self.client.get("/campaigns").json()["campaigns"]
        self.assertIn("camp-pr", [c["id"] for c in campaigns])

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

    def test_campaign_real_ai_step_openai_compat_uses_base_url(self) -> None:
        """A4: a real-AI campaign step bound to an openai_compat backend passes the
        backend's base_url to build_llm -- the step runs keyless against a local
        OpenAI-wire stub server, end to end."""
        import json
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer

        received: list[str] = []

        class _StubOpenAi(BaseHTTPRequestHandler):
            def log_message(self, *args: object) -> None:
                return

            def do_POST(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
                received.append(self.path)
                payload = json.dumps({"choices": [{"message": {"content": "done"}}]}).encode(
                    "utf-8"
                )
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        server = HTTPServer(("127.0.0.1", 0), _StubOpenAi)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            self.config.add_ai_backend(
                {
                    "id": "b-compat",
                    "provider": "openai_compat",
                    "model": "qwen2.5",
                    "base_url": f"http://127.0.0.1:{port}/v1",
                }
            )
            self.config.add_agent(
                {
                    "id": "gh-real",
                    "runtime": "lab",
                    "principal": "bot@acme",
                    "target_system": "github",
                    "goal": "open a PR",
                    "capability_scope": ["read_repo", "open_pr"],
                    "ai_mode": "real",
                    "ai_backend_id": "b-compat",
                }
            )
            created = self.client.post(
                "/campaigns",
                json={
                    "id": "camp-real",
                    "description": "real-AI step",
                    "steps": [{"agent_id": "gh-real"}],
                },
            )
            self.assertEqual(created.status_code, 201)
            run_id = self.client.post("/campaigns/camp-real/run").json()["run_id"]
            self.assertEqual(_wait_terminal(self.client, run_id)["status"], "completed")
            events = self.client.get(f"/runs/{run_id}/events").json()
            start = next(e for e in events if e["type"] == "agent_start")
            self.assertEqual(start["data"]["provider"], "openai_compat")
            self.assertFalse(any(e["type"] == "step_error" for e in events))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
        self.assertEqual(received, ["/v1/chat/completions"])

    def test_run_unknown_campaign_404(self) -> None:
        self.assertEqual(self.client.post("/campaigns/nope/run").status_code, 404)

    def test_create_duplicate_400(self) -> None:
        steps = [{"agent_id": "gh-pr-bot", "stub_script": _STUB}]
        body = {"id": "dup", "description": "", "steps": steps}
        self.assertEqual(self.client.post("/campaigns", json=body).status_code, 201)
        self.assertEqual(self.client.post("/campaigns", json=body).status_code, 400)

    def test_replay_unknown_recording_404(self) -> None:
        self.assertEqual(self.client.post("/recordings/nope/replay").status_code, 404)

    def test_templates_listed_and_instantiate_seeds_agent_and_campaign(self) -> None:
        templates = self.client.get("/campaign-templates").json()["templates"]
        self.assertTrue(len(templates) >= 10)
        tid = "finance-wire-fraud"
        self.assertIn(tid, [t["id"] for t in templates])

        # Instantiate seeds the mock agent and the campaign.
        self.assertEqual(
            self.client.post(f"/campaign-templates/{tid}/instantiate").status_code, 201
        )
        self.assertIn(tid, [c["id"] for c in self.client.get("/campaigns").json()["campaigns"]])
        agent = self.client.get("/config/agents").json()
        self.assertIn(f"{tid}-agent", [a["id"] for a in agent])

        # The instantiated mock campaign runs its scenario end to end.
        run_id = self.client.post(f"/campaigns/{tid}/run").json()["run_id"]
        self.assertEqual(_wait_terminal(self.client, run_id)["status"], "completed")
        events = self.client.get(f"/runs/{run_id}/events").json()
        steps = [
            e["data"]["action"]["action_type"]
            for e in events
            if e["type"] == "step" and e["data"].get("action")
        ]
        self.assertIn("launch_wire_transfer", steps)

    def test_instantiate_unknown_template_404(self) -> None:
        self.assertEqual(self.client.post("/campaign-templates/nope/instantiate").status_code, 404)
