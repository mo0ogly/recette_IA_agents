"""GET /capture/llm-traces returns a run's in-process hook capture."""

from __future__ import annotations

import unittest

try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app
    from recette.capture.llm_trace import LlmCallTrace

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover - only without the [api] extra
    _HAS_FASTAPI = False


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class TestCaptureApi(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app()
        self.client = TestClient(self.app)

    def test_unknown_run_returns_empty(self) -> None:
        resp = self.client.get("/capture/llm-traces", params={"run_id": "nope"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"run_id": "nope", "traces": [], "count": 0})

    def test_returns_recorded_traces_for_a_run(self) -> None:
        self.app.state.capture_store.record(
            "run-1",
            LlmCallTrace(
                seq=1,
                event_id="LC000001",
                agent_id="a1",
                model="m",
                kind="tool_call",
                tool_name="read_repo",
                resource="acme/x",
                prompt_tokens=5,
                completion_tokens=1,
                latency_ms=42,
                error=None,
            ),
        )
        resp = self.client.get("/capture/llm-traces", params={"run_id": "run-1"})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["traces"][0]["intent"], "read_repo:acme/x")
        self.assertEqual(body["traces"][0]["total_tokens"], 6)


if __name__ == "__main__":
    unittest.main()
