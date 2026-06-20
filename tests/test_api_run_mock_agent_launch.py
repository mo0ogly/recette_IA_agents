import unittest

try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover - depends on the [api] extra
    _HAS_FASTAPI = False


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class MockAgentLaunchTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())
        # register a server + a MOCK agent (ai_mode=mock, a scenario, NO ai_backend_id)
        self.client.post(
            "/config/servers",
            json={"id": "t-gh", "system": "github", "mode": "mock_local", "port": 9151},
        )
        self.client.post("/config/servers/t-gh/start")
        self.client.post(
            "/config/agents",
            json={
                "id": "t-mock-bot",
                "runtime": "lab",
                "ai_mode": "mock",
                "principal": "t@acme",
                "target_system": "github",
                "goal": "mock launch proof",
                "capability_scope": ["read_repo"],
                "server": "t-gh",
                "scenario": [
                    {
                        "kind": "tool_call",
                        "tool_name": "read_repo",
                        "tool_args": {"resource": "acme/x"},
                    },
                    {"kind": "final", "text": "done"},
                ],
            },
        )

    def tearDown(self) -> None:
        self.client.post("/config/servers/t-gh/stop")
        self.client.delete("/config/agents/t-mock-bot")
        self.client.delete("/config/servers/t-gh")

    def test_lane_b_launches_mock_agent_without_backend(self) -> None:
        r = self.client.post("/runs", json={"kind": "lane_b", "params": {"agent_id": "t-mock-bot"}})
        self.assertEqual(r.status_code, 201, r.text)
        self.assertIn("run_id", r.json())


if __name__ == "__main__":
    unittest.main()
