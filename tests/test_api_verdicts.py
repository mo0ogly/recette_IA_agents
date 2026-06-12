"""Verdict ingestion + ground-truth judging (POST/GET /verdicts).

External discovery/identification tools submit their results; the API judges
each result against the agent's stored ground_truth block and persists the
judged submission. The judge is a pure function (I4): no clock, no randomness.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from recette.api.app import create_app
from recette.api.config_store import ConfigStore
from recette.api.verdict_store import VerdictStore, judge
from recette.platform.catalog import Catalog
from recette.platform.catalog.model import ActionSpec, RiskLevel
from recette.platform.events import PolicyVerdict
from recette.platform.eventstore.memory_store import InMemoryEventStore
from recette.platform.policy.store import PolicyStore
from recette.platform.proxy.protocol import ExecutionResult, side_effect_hash

SPECS = (
    ActionSpec(
        target_system="okta",
        action_type="list_users",
        risk_level=RiskLevel.LOW,
        verdict_privileged=PolicyVerdict.ALLOW,
        verdict_default=PolicyVerdict.DENY,
        privileged_roles=("identity_admin",),
        description="List users (read-only)",
    ),
)

FULL_GROUND_TRUTH = {
    "detectable": True,
    "expected_identity": "bot@acme",
    "dimensions": {"identity": True, "capabilities": True, "policy": True, "behavior": True},
    "expected_verdict": "correct",
}

MATCHING_RESULT = {
    "detected": True,
    "identity": "bot@acme",
    "dimensions": {"identity": True, "capabilities": True, "policy": True, "behavior": True},
    "verdict": "correct",
}


class StubProxy:
    def execute(self, event) -> ExecutionResult:  # type: ignore[no-untyped-def]
        response = {"done": True}
        return ExecutionResult(
            ok=True,
            status_code=200,
            response=response,
            side_effect_hash=side_effect_hash(
                event.target_system, event.action_type, event.resource, response
            ),
        )


class TestJudge(unittest.TestCase):
    def test_empty_ground_truth_is_skip_never_pass_by_vacuity(self) -> None:
        verdict = judge({}, {"detected": True}, [])
        self.assertEqual(verdict["status"], "SKIP")
        self.assertEqual(verdict["checks"], {})

    def test_full_match_is_pass(self) -> None:
        verdict = judge(FULL_GROUND_TRUTH, MATCHING_RESULT, ["EV1"])
        self.assertEqual(verdict["status"], "PASS")
        self.assertEqual(
            verdict["checks"],
            {
                "detected": True,
                "verdict": True,
                "identity_claim": True,
                "dimension:identity": True,
                "dimension:capabilities": True,
                "dimension:policy": True,
                "dimension:behavior": True,
            },
        )
        self.assertEqual(verdict["expected"], FULL_GROUND_TRUTH)
        self.assertEqual(verdict["observed"], MATCHING_RESULT)
        self.assertEqual(verdict["evidence_event_ids"], ["EV1"])

    def test_detected_mismatch_is_fail(self) -> None:
        verdict = judge({"detectable": True}, {"detected": False}, [])
        self.assertEqual(verdict["status"], "FAIL")
        self.assertEqual(verdict["checks"], {"detected": False})

    def test_partial_dimensions_check_only_declared_ones(self) -> None:
        ground_truth = {"dimensions": {"identity": True, "policy": False}}
        result = {"dimensions": {"identity": True, "policy": False, "behavior": False}}
        verdict = judge(ground_truth, result, [])
        self.assertEqual(verdict["status"], "PASS")
        self.assertEqual(
            verdict["checks"], {"dimension:identity": True, "dimension:policy": True}
        )

    def test_missing_result_field_fails_the_check(self) -> None:
        verdict = judge({"expected_identity": "bot@acme"}, {}, [])
        self.assertEqual(verdict["status"], "FAIL")
        self.assertEqual(verdict["checks"], {"identity_claim": False})


class TestVerdictStore(unittest.TestCase):
    def test_append_latest_history_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = VerdictStore(Path(tmp) / "verdicts.json")
            self.assertIsNone(store.latest())
            self.assertEqual(store.history(), [])
            store.append({"tool": "t1", "judged": []})
            store.append({"tool": "t2", "judged": []})
            self.assertEqual(store.latest()["tool"], "t2")
            self.assertEqual([s["tool"] for s in store.history()], ["t1", "t2"])
            # a fresh store over the same file sees the same submissions
            self.assertEqual(VerdictStore(Path(tmp) / "verdicts.json").latest()["tool"], "t2")


class TestVerdictsApi(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tmp = Path(self._tmp.name)
        self.event_store = InMemoryEventStore()
        self.app = create_app(
            config_store=ConfigStore(tmp / "config.json"),
            event_store=self.event_store,
            policy_store=PolicyStore(tmp / "policies"),
            proxy=StubProxy(),
            catalog=Catalog(SPECS),
            verdict_store=VerdictStore(tmp / "verdicts.json"),
        )
        self.client = TestClient(self.app)
        for agent in (
            {
                "id": "agent-gt",
                "runtime": "lab",
                "role": "identity_admin",
                "capability_scope": ["okta"],
                "ground_truth": FULL_GROUND_TRUTH,
            },
            {
                "id": "agent-nogt",
                "runtime": "lab",
                "role": "identity_admin",
                "capability_scope": ["okta"],
            },
        ):
            resp = self.client.post("/config/agents", json=agent)
            self.assertEqual(resp.status_code, 201, resp.text)

    def _seed_event(self, agent_id: str) -> None:
        resp = self.client.post(
            "/actions/execute",
            json={
                "agent_id": agent_id,
                "action_type": "list_users",
                "target_system": "okta",
                "resource": "org/acme",
                "payload": {"reason": "seed"},
            },
        )
        self.assertEqual(resp.status_code, 200, resp.text)

    def test_pass_case_with_full_ground_truth(self) -> None:
        resp = self.client.post(
            "/verdicts",
            json={"tool": "discovery-v1", "results": [{"agent_id": "agent-gt", **MATCHING_RESULT}]},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(len(body["judged"]), 1)
        entry = body["judged"][0]
        self.assertEqual(entry["agent_id"], "agent-gt")
        self.assertEqual(entry["status"], "PASS")
        self.assertTrue(all(entry["checks"].values()))

    def test_fail_on_detected_mismatch_with_evidence_event_ids(self) -> None:
        self._seed_event("agent-gt")
        events = self.event_store.read_from(0, agent_id="agent-gt")
        self.assertGreater(len(events), 0)
        resp = self.client.post(
            "/verdicts",
            json={
                "tool": "discovery-v1",
                "results": [{"agent_id": "agent-gt", **MATCHING_RESULT, "detected": False}],
            },
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        entry = resp.json()["judged"][0]
        self.assertEqual(entry["status"], "FAIL")
        self.assertFalse(entry["checks"]["detected"])
        self.assertEqual(entry["evidence_event_ids"], [e.event_id for e in events])

    def test_unknown_agent_is_fail_entry(self) -> None:
        resp = self.client.post(
            "/verdicts",
            json={"tool": "discovery-v1", "results": [{"agent_id": "ghost", "detected": True}]},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        entry = resp.json()["judged"][0]
        self.assertEqual(entry["agent_id"], "ghost")
        self.assertEqual(entry["status"], "FAIL")
        self.assertEqual(entry["error"], "unknown agent")

    def test_agent_without_ground_truth_is_skip(self) -> None:
        resp = self.client.post(
            "/verdicts",
            json={"tool": "discovery-v1", "results": [{"agent_id": "agent-nogt", "detected": True}]},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        entry = resp.json()["judged"][0]
        self.assertEqual(entry["agent_id"], "agent-nogt")
        self.assertEqual(entry["status"], "SKIP")

    def test_malformed_result_entry_is_fail_never_500(self) -> None:
        resp = self.client.post(
            "/verdicts",
            json={"tool": "discovery-v1", "results": ["not-a-dict", {"detected": True}]},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        judged = resp.json()["judged"]
        self.assertEqual([e["status"] for e in judged], ["FAIL", "FAIL"])
        for entry in judged:
            self.assertIn("error", entry)

    def test_results_must_be_a_list(self) -> None:
        resp = self.client.post("/verdicts", json={"tool": "t", "results": "nope"})
        self.assertEqual(resp.status_code, 400, resp.text)

    def test_submitted_seq_is_current_max_event_seq(self) -> None:
        self._seed_event("agent-gt")
        self._seed_event("agent-nogt")
        all_events = self.event_store.read_from(0)
        resp = self.client.post(
            "/verdicts",
            json={"tool": "discovery-v1", "results": [{"agent_id": "agent-gt", **MATCHING_RESULT}]},
        )
        self.assertEqual(resp.json()["submitted_seq"], all_events[-1].seq)

    def test_submitted_seq_is_zero_on_empty_store(self) -> None:
        resp = self.client.post("/verdicts", json={"tool": "t", "results": []})
        self.assertEqual(resp.json()["submitted_seq"], 0)

    def test_get_latest_returns_last_submission(self) -> None:
        self.client.post("/verdicts", json={"tool": "first", "results": []})
        self.client.post(
            "/verdicts",
            json={"tool": "second", "results": [{"agent_id": "agent-gt", **MATCHING_RESULT}]},
        )
        resp = self.client.get("/verdicts")
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["tool"], "second")
        self.assertEqual(body["judged"][0]["status"], "PASS")
        history = self.client.get("/verdicts/history")
        self.assertEqual(history.status_code, 200, history.text)
        self.assertEqual([s["tool"] for s in history.json()], ["first", "second"])

    def test_get_latest_404_when_empty(self) -> None:
        resp = self.client.get("/verdicts")
        self.assertEqual(resp.status_code, 404, resp.text)
        history = self.client.get("/verdicts/history")
        self.assertEqual(history.status_code, 200, history.text)
        self.assertEqual(history.json(), [])


class TestVerdictScorecard(unittest.TestCase):
    """GET /verdicts/scorecard aggregates over the latest judged submission."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tmp = Path(self._tmp.name)
        self.app = create_app(
            config_store=ConfigStore(tmp / "config.json"),
            event_store=InMemoryEventStore(),
            policy_store=PolicyStore(tmp / "policies"),
            proxy=StubProxy(),
            catalog=Catalog(SPECS),
            verdict_store=VerdictStore(tmp / "verdicts.json"),
        )
        self.client = TestClient(self.app)
        for agent in (
            # PASS: full ground truth, matching result.
            {"id": "agent-pass", "runtime": "lab", "ground_truth": FULL_GROUND_TRUTH},
            # FAIL false negative: detectable but the tool reports detected=false.
            {
                "id": "agent-fn",
                "runtime": "lab",
                "ground_truth": {"detectable": True, "dimensions": {"identity": True}},
            },
            # FAIL false positive: not detectable but the tool reports detected=true.
            {"id": "agent-fp", "runtime": "lab", "ground_truth": {"detectable": False}},
            # SKIP: no ground truth declared.
            {"id": "agent-skip", "runtime": "lab"},
        ):
            resp = self.client.post("/config/agents", json=agent)
            self.assertEqual(resp.status_code, 201, resp.text)

    def _submit_four_agents(self) -> None:
        resp = self.client.post(
            "/verdicts",
            json={
                "tool": "discovery-v1",
                "results": [
                    {"agent_id": "agent-pass", **MATCHING_RESULT},
                    {
                        "agent_id": "agent-fn",
                        "detected": False,
                        "dimensions": {"identity": False},
                    },
                    {"agent_id": "agent-fp", "detected": True},
                    {"agent_id": "agent-skip", "detected": True},
                ],
            },
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(
            [e["status"] for e in resp.json()["judged"]], ["PASS", "FAIL", "FAIL", "SKIP"]
        )

    def test_scorecard_aggregates_every_field(self) -> None:
        self._submit_four_agents()
        resp = self.client.get("/verdicts/scorecard")
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["total"], 4)
        self.assertEqual(body["passed"], 1)
        self.assertEqual(body["skipped"], 1)
        # 3 agents carry a detected-check; only agent-pass matched.
        self.assertEqual(body["detection_rate"], round(1 / 3, 4))
        # identity checked on agent-pass (ok) and agent-fn (miss); the other
        # 3 dimensions only on agent-pass (ok).
        self.assertEqual(
            body["accuracy_by_dimension"],
            {"identity": 0.5, "capabilities": 1.0, "policy": 1.0, "behavior": 1.0},
        )
        self.assertEqual(body["false_positives"], 1)
        self.assertEqual(body["false_negatives"], 1)

    def test_scorecard_null_rates_when_no_checks(self) -> None:
        self.client.post(
            "/verdicts",
            json={"tool": "t", "results": [{"agent_id": "agent-skip", "detected": True}]},
        )
        body = self.client.get("/verdicts/scorecard").json()
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["passed"], 0)
        self.assertEqual(body["skipped"], 1)
        self.assertIsNone(body["detection_rate"])
        self.assertEqual(
            body["accuracy_by_dimension"],
            {"identity": None, "capabilities": None, "policy": None, "behavior": None},
        )
        self.assertEqual(body["false_positives"], 0)
        self.assertEqual(body["false_negatives"], 0)

    def test_scorecard_404_when_no_submission(self) -> None:
        resp = self.client.get("/verdicts/scorecard")
        self.assertEqual(resp.status_code, 404, resp.text)


if __name__ == "__main__":
    unittest.main()
