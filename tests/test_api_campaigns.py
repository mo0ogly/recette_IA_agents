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

    def test_campaign_runs_each_agent_on_its_own_provider(self) -> None:
        """Multi-provider proof: in a SINGLE campaign, agent_a is bound to backend_a
        and agent_b to backend_b. The runner builds one LlmBackend per step from the
        agent's own ai_backend (runners.py build_llm call inside the step loop), so each
        agent must reach ITS OWN provider. Two distinct local OpenAI-wire stub servers
        each return a distinct final answer and record their hits; the persisted
        recordings prove agent_a got "from-A" and agent_b got "from-B"."""
        import json
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer

        def _make_stub(answer: str, hits: list[str]):
            class _StubOpenAi(BaseHTTPRequestHandler):
                def log_message(self, *args: object) -> None:
                    return

                def do_POST(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
                    hits.append(self.path)
                    payload = json.dumps({"choices": [{"message": {"content": answer}}]}).encode(
                        "utf-8"
                    )
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)

            return _StubOpenAi

        hits_a: list[str] = []
        hits_b: list[str] = []
        server_a = HTTPServer(("127.0.0.1", 0), _make_stub("from-A", hits_a))
        server_b = HTTPServer(("127.0.0.1", 0), _make_stub("from-B", hits_b))
        port_a = server_a.server_address[1]
        port_b = server_b.server_address[1]
        thread_a = threading.Thread(target=server_a.serve_forever, daemon=True)
        thread_b = threading.Thread(target=server_b.serve_forever, daemon=True)
        thread_a.start()
        thread_b.start()

        def _shutdown() -> None:
            server_a.shutdown()
            server_a.server_close()
            thread_a.join(timeout=5)
            server_b.shutdown()
            server_b.server_close()
            thread_b.join(timeout=5)

        self.addCleanup(_shutdown)

        # Two distinct backends, both openai_compat but different base_url + model.
        self.config.add_ai_backend(
            {
                "id": "backend_a",
                "provider": "openai_compat",
                "model": "model-a",
                "base_url": f"http://127.0.0.1:{port_a}/v1",
            }
        )
        self.config.add_ai_backend(
            {
                "id": "backend_b",
                "provider": "openai_compat",
                "model": "model-b",
                "base_url": f"http://127.0.0.1:{port_b}/v1",
            }
        )
        self.config.add_agent(
            {
                "id": "agent_a",
                "runtime": "lab",
                "principal": "bot-a@acme",
                "target_system": "github",
                "goal": "ask provider A",
                "capability_scope": ["read_repo"],
                "ai_mode": "real",
                "ai_backend_id": "backend_a",
            }
        )
        self.config.add_agent(
            {
                "id": "agent_b",
                "runtime": "lab",
                "principal": "bot-b@acme",
                "target_system": "github",
                "goal": "ask provider B",
                "capability_scope": ["read_repo"],
                "ai_mode": "real",
                "ai_backend_id": "backend_b",
            }
        )

        # One campaign that runs BOTH agents.
        created = self.client.post(
            "/campaigns",
            json={
                "id": "camp-multi",
                "description": "two agents, two providers",
                "steps": [{"agent_id": "agent_a"}, {"agent_id": "agent_b"}],
            },
        )
        self.assertEqual(created.status_code, 201)
        run_id = self.client.post("/campaigns/camp-multi/run").json()["run_id"]
        self.assertEqual(_wait_terminal(self.client, run_id)["status"], "completed")

        events = self.client.get(f"/runs/{run_id}/events").json()
        self.assertFalse(any(e["type"] == "step_error" for e in events))
        # Both agents ran in the same campaign and each reported its own provider.
        starts = {
            e["data"]["agent_id"]: e["data"]["provider"]
            for e in events
            if e["type"] == "agent_start"
        }
        self.assertEqual(starts, {"agent_a": "openai_compat", "agent_b": "openai_compat"})

        # Each stub server was hit exactly once on the chat endpoint -- proof that
        # each agent ran on ITS OWN provider, not a single shared backend.
        self.assertEqual(hits_a, ["/v1/chat/completions"])
        self.assertEqual(hits_b, ["/v1/chat/completions"])

        # The persisted recordings carry the distinct final answers, proving the
        # routing reached the intended server per agent (agent_a -> A, agent_b -> B).
        recs = {r["recording_id"]: r for r in self.client.get("/recordings").json()["recordings"]}
        rec_a_id = next(rid for rid in recs if rid.endswith(".agent_a"))
        rec_b_id = next(rid for rid in recs if rid.endswith(".agent_b"))
        rec_a = self.client.get(f"/recordings/{rec_a_id}").json()
        rec_b = self.client.get(f"/recordings/{rec_b_id}").json()
        self.assertEqual(rec_a["model"], "model-a")
        self.assertEqual(rec_b["model"], "model-b")
        final_a = rec_a["steps"][-1]["decision"]["text"]
        final_b = rec_b["steps"][-1]["decision"]["text"]
        self.assertEqual(final_a, "from-A")
        self.assertEqual(final_b, "from-B")

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
