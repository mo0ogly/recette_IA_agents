# tests/test_verdict.py
"""F1: judge a live run's action log against the agent's declared manifest.

judge_run is a pure, deterministic function of (agent config, action log) reusing
the reference identification adapter (I4). It connects the visible communication
to the recette object: identity / capabilities / policy / behavior + verdict.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from recette.api.verdict import (
    action_log_from_run_events,
    config_agent_to_manifest,
    judge_run,
    verdict_payload,
)
from recette.events import AgentAction

try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app
    from recette.api.config_store import ConfigStore
    from recette.platform.eventstore.memory_store import InMemoryEventStore

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover - depends on the [api] extra
    _HAS_FASTAPI = False


def _action(
    action_type: str,
    *,
    principal: str = "bot@acme",
    mode: str = "read",
    resource: str = "acme/x",
    approved: bool = False,
    seq: int = 1,
) -> AgentAction:
    return AgentAction(
        event_id=f"evt-{seq:04d}",
        seq=seq,
        timestamp="2026-06-14T00:00:00Z",
        agent_id="a1",
        principal=principal,
        target_system="github",
        action_type=action_type,
        mode=mode,
        resource=resource,
        approved=approved,
    )


CORRECT_CFG = {
    "id": "a1",
    "principal": "bot@acme",
    "capability_scope": ["read_repo", "open_pr"],
}


class ManifestMappingTests(unittest.TestCase):
    def test_config_scope_becomes_grants_with_canonical_mode(self) -> None:
        manifest = config_agent_to_manifest(CORRECT_CFG)
        self.assertEqual(manifest["declared_identity"]["principal"], "bot@acme")
        grants = {g["action"]: g for g in manifest["capability_scope"]}
        self.assertEqual(grants["read_repo"]["mode"], "read")
        self.assertEqual(grants["open_pr"]["mode"], "write")
        self.assertEqual(grants["read_repo"]["resources"], ["*"])

    def test_empty_scope_agent_yields_empty_grants(self) -> None:
        manifest = config_agent_to_manifest({"principal": "p", "capability_scope": []})
        self.assertEqual(manifest["capability_scope"], [])


class JudgeRunTests(unittest.TestCase):
    def test_in_scope_run_is_correct_on_all_dimensions(self) -> None:
        log = [_action("read_repo", seq=1), _action("open_pr", mode="write", seq=2)]
        result = judge_run(CORRECT_CFG, log)
        self.assertTrue(result.identity_match)
        self.assertTrue(result.capabilities_conform)
        self.assertTrue(result.policy_compliant)
        self.assertTrue(result.behavior_expected)
        self.assertEqual(result.verdict, "correct")

    def test_out_of_scope_action_is_incorrect_with_typed_violation(self) -> None:
        log = [_action("read_repo", seq=1), _action("delete_user", mode="write", seq=2)]
        result = judge_run(CORRECT_CFG, log)
        self.assertFalse(result.capabilities_conform)
        self.assertEqual(result.verdict, "incorrect")
        kinds = {v.kind for v in result.capability_violations}
        self.assertIn("undeclared_action", kinds)

    def test_identity_mismatch_is_incorrect(self) -> None:
        log = [_action("read_repo", principal="someone-else@acme")]
        result = judge_run(CORRECT_CFG, log)
        self.assertFalse(result.identity_match)
        self.assertEqual(result.verdict, "incorrect")

    def test_non_git_action_does_not_crash_policy(self) -> None:
        # okta/finance actions are not git ActionType members; the judge must
        # treat them as policy-compliant here, never raise.
        cfg = {"principal": "ops@acme", "capability_scope": ["suspend_user", "reset_password"]}
        log = [_action("suspend_user", principal="ops@acme", mode="write", resource="acme/jdoe")]
        result = judge_run(cfg, log)
        self.assertTrue(result.policy_compliant)
        self.assertEqual(result.verdict, "correct")

    def test_empty_action_log_is_judgeable(self) -> None:
        # An inert empty-scope agent (0 action) yields a defined verdict, no crash.
        result = judge_run({"principal": "p", "capability_scope": []}, [])
        self.assertEqual(result.verdict, "correct")

    def test_is_deterministic(self) -> None:
        log = [_action("read_repo", seq=1), _action("delete_user", mode="write", seq=2)]
        a = verdict_payload(judge_run(CORRECT_CFG, log))
        b = verdict_payload(judge_run(CORRECT_CFG, log))
        self.assertEqual(a, b)


class ActionLogExtractionTests(unittest.TestCase):
    def test_extracts_actions_from_result_frame(self) -> None:
        events = [
            {"type": "start", "data": {"kind": "lane_b"}},
            {"type": "step", "data": {"index": 0}},
            {
                "type": "result",
                "data": {"actions": [_action("read_repo", seq=1).to_dict()]},
            },
            {"type": "end", "data": {"status": "completed"}},
        ]
        log = action_log_from_run_events(events)
        self.assertEqual([a.action_type for a in log], ["read_repo"])

    def test_no_result_frame_yields_empty_log(self) -> None:
        events = [{"type": "start", "data": {}}, {"type": "end", "data": {}}]
        self.assertEqual(action_log_from_run_events(events), [])


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class VerdictEndpointTests(unittest.TestCase):
    _STUB = [
        {"kind": "tool_call", "tool_name": "read_repo", "tool_args": {"resource": "acme/x"}},
        {"kind": "tool_call", "tool_name": "open_pr", "tool_args": {"resource": "acme/x"}},
        {"kind": "final", "text": "done"},
    ]

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        store = ConfigStore(Path(self._tmp.name) / "cfg.json")
        store.add_agent(
            {
                "id": "ci-bot",
                "principal": "acme-bot@github",
                "target_system": "github",
                "goal": "bump deps",
                "capability_scope": ["read_repo", "open_pr"],
                "runtime": "lab",
            }
        )
        self._client = TestClient(create_app(config_store=store, event_store=InMemoryEventStore()))

    def _run_to_completion(self) -> str:
        import time

        r = self._client.post(
            "/runs",
            json={"kind": "lane_b", "params": {"agent_id": "ci-bot", "stub_script": self._STUB}},
        )
        self.assertEqual(r.status_code, 201, r.text)
        run_id = r.json()["run_id"]
        for _ in range(200):
            if self._client.get(f"/runs/{run_id}").json()["status"] == "completed":
                break
            time.sleep(0.01)
        return run_id

    def test_verdict_of_in_scope_run_is_correct(self) -> None:
        run_id = self._run_to_completion()
        body = self._client.get(f"/runs/{run_id}/verdict").json()
        self.assertEqual(body["agent_id"], "ci-bot")
        self.assertEqual(body["verdict"], "correct")
        self.assertTrue(body["dimensions"]["capabilities"])
        self.assertEqual(body["action_count"], 2)

    def test_verdict_404_for_unknown_run(self) -> None:
        self.assertEqual(self._client.get("/runs/nope/verdict").status_code, 404)


if __name__ == "__main__":
    unittest.main()
