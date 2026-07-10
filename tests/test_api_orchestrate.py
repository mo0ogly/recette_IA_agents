"""Live orchestration endpoints (POST /orchestrate/run + GET /orchestrate/sessions).

Deterministic: build_llm is patched to hand back scripted StubLlm backends (one
per participant, in participant order), so the whole live path runs offline with
no provider key -- exactly how recette.orchestrate is tested. The real path swaps
StubLlm for a live backend; the endpoint contract is identical.
"""

import unittest
from unittest import mock

try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app
    from recette.llm import LlmDecision, StubLlm

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover - depends on the [api] extra
    _HAS_FASTAPI = False


HANDOFF_TEAM = {
    "kind": "maf_orchestration",
    "agent_id": "drive-handoff",
    "name": "Drive Handoff",
    "start_agent": "triage",
    "termination": {"max_hops": 8},
    "participants": [
        {
            "agent_id": "triage",
            "declared_identity": {"provider": "AzureOpenAI", "model": "m"},
            "handoffs": [{"target": "worker"}],
        },
        {
            "agent_id": "worker",
            "declared_identity": {"provider": "AzureOpenAI", "model": "m"},
            "handoffs": [{"target": "triage"}],
            "tools": [{"tool_kind": "mcp", "target": "mcp://x", "approval": "always"}],
        },
    ],
}


def _tc(name: str, **args) -> "LlmDecision":
    return LlmDecision(kind="tool_call", tool_name=name, tool_args=args)


_FINAL = LlmDecision(kind="final", text="done")


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class OrchestrateRunTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def _scripted_build_llm(self):
        # One StubLlm per participant, returned in participant iteration order
        # (triage then worker): triage hands off, worker acts then finalises.
        scripts = iter(
            [
                StubLlm([_tc("handoff_to_worker")]),
                StubLlm([_tc("use_mcp_0", approved=True), _FINAL]),
            ]
        )
        return lambda *a, **k: next(scripts)

    def test_run_drives_tracks_and_judges(self) -> None:
        with mock.patch("recette.llm.build_llm", side_effect=self._scripted_build_llm()):
            r = self.client.post(
                "/orchestrate/run",
                json={
                    "team": HANDOFF_TEAM,
                    "providers": {"provider": "groq", "model": "m"},
                    "session_id": "sess-1",
                },
            )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["session_id"], "sess-1")
        self.assertIn(body["verdict"], {"correct", "incorrect"})
        # The handoff produced a hop triage -> worker and the worker's tool call.
        self.assertTrue(
            any(h["from"] == "triage" and h["to"] == "worker" for h in body["run"]["hops"])
        )
        self.assertTrue(any(a["agent_id"] == "worker" for a in body["run"]["actions"]))
        # Tracking recorded the session with its instances.
        self.assertIn("triage", body["instances"])

    def test_unknown_provider_is_422(self) -> None:
        r = self.client.post(
            "/orchestrate/run",
            json={
                "team": HANDOFF_TEAM,
                "providers": {"provider": "no-such-provider", "model": "m"},
                "session_id": "sess-x",
            },
        )
        self.assertEqual(r.status_code, 422)

    def test_missing_session_id_is_422(self) -> None:
        r = self.client.post(
            "/orchestrate/run",
            json={"team": HANDOFF_TEAM, "providers": {"provider": "groq", "model": "m"}},
        )
        self.assertEqual(r.status_code, 422)

    def test_invalid_team_is_422(self) -> None:
        r = self.client.post(
            "/orchestrate/run",
            json={
                "team": {"not": "a team"},
                "providers": {"provider": "groq", "model": "m"},
                "session_id": "s",
            },
        )
        self.assertEqual(r.status_code, 422)

    def test_sessions_listing_and_detail_after_a_run(self) -> None:
        with mock.patch("recette.llm.build_llm", side_effect=self._scripted_build_llm()):
            self.client.post(
                "/orchestrate/run",
                json={
                    "team": HANDOFF_TEAM,
                    "providers": {"provider": "groq", "model": "m"},
                    "session_id": "sess-2",
                },
            )
        listing = self.client.get("/orchestrate/sessions").json()
        self.assertTrue(any(s["session_id"] == "sess-2" for s in listing["sessions"]))
        detail = self.client.get("/orchestrate/sessions/sess-2").json()
        self.assertEqual(detail["session_id"], "sess-2")
        self.assertTrue(detail["verify"]["ok"])
        self.assertGreater(len(detail["receipts"]), 0)

    def test_unknown_session_is_404(self) -> None:
        r = self.client.get("/orchestrate/sessions/nope")
        self.assertEqual(r.status_code, 404)

    def test_run_forces_wire_route_when_overlay_is_up(self) -> None:
        # With the overlay up (wire_proxy_url set), every backend must be built
        # with that proxy_url so the run's LLM bytes are captured on the wire.
        app = create_app()
        app.state.wire_proxy_url = "http://127.0.0.1:8083"
        client = TestClient(app)
        seen: list[str | None] = []

        scripts = iter(
            [
                StubLlm([_tc("handoff_to_worker")]),
                StubLlm([_tc("use_mcp_0", approved=True), _FINAL]),
            ]
        )

        def _capture(*_a, **kw):
            seen.append(kw.get("proxy_url"))
            return next(scripts)

        with mock.patch("recette.llm.build_llm", side_effect=_capture):
            r = client.post(
                "/orchestrate/run",
                json={
                    "team": HANDOFF_TEAM,
                    "providers": {"provider": "groq", "model": "m"},
                    "session_id": "sess-wire",
                },
            )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["wire_captured"])
        # Both participants' backends were built routed through the overlay.
        self.assertEqual(seen, ["http://127.0.0.1:8083", "http://127.0.0.1:8083"])

    def test_run_stays_direct_when_overlay_is_off(self) -> None:
        # Overlay off (wire_proxy_url None): backends are direct, and the
        # response says so, so the operator knows the deep-links will be empty.
        seen: list[str | None] = []
        scripts = iter(
            [
                StubLlm([_tc("handoff_to_worker")]),
                StubLlm([_tc("use_mcp_0", approved=True), _FINAL]),
            ]
        )

        def _capture(*_a, **kw):
            seen.append(kw.get("proxy_url"))
            return next(scripts)

        with mock.patch("recette.llm.build_llm", side_effect=_capture):
            r = self.client.post(
                "/orchestrate/run",
                json={
                    "team": HANDOFF_TEAM,
                    "providers": {"provider": "groq", "model": "m"},
                    "session_id": "sess-direct",
                },
            )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse(r.json()["wire_captured"])
        self.assertEqual(seen, [None, None])


if __name__ == "__main__":
    unittest.main()
