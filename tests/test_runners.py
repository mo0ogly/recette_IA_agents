"""Unit recette for run bodies (recette/api/runners.py).

Hardens the agent/server functioning paths that had no dedicated unit
coverage: proxy-mediated execution (I5), fail-safe forge routing, every
campaign-step error branch, and deterministic replay (I4). No HTTP, no
FastAPI: runners are pure orchestration, so these tests run everywhere.
"""

from __future__ import annotations

import unittest

import recette.api.runners as runners_mod
from recette.api.runners import (
    GatewayForge,
    ProxyForge,
    build_stub_llm,
    forge_for_agent,
    make_campaign_runner,
    make_lane_b_runner,
    make_replay_runner,
)
from recette.forge import LabForge
from recette.lane_b import run_agent
from recette.llm import LlmDecision, StubLlm
from recette.platform.catalog.model import RISK_SCORE, RiskLevel
from recette.platform.events import PlatformActionEvent
from recette.platform.gateway import ActionOutcome
from recette.platform.proxy.protocol import ExecutionResult, side_effect_hash

READ_THEN_FINAL: list[dict] = [
    {"kind": "tool_call", "tool_name": "read_repo", "tool_args": {"resource": "acme/x"}},
    {"kind": "final", "text": "done"},
]


class OkProxy:
    """Deterministic proxy stub: succeeds and captures every event (I5 seam)."""

    def __init__(self) -> None:
        self.events: list[PlatformActionEvent] = []

    def execute(self, event: PlatformActionEvent) -> ExecutionResult:
        self.events.append(event)
        response = {"done": True}
        return ExecutionResult(
            ok=True,
            status_code=200,
            response=response,
            side_effect_hash=side_effect_hash(
                event.target_system, event.action_type, event.resource, response
            ),
        )


class FailProxy:
    def execute(self, event: PlatformActionEvent) -> ExecutionResult:
        return ExecutionResult(ok=False, status_code=502, error="lab server unreachable")


class TestProxyForge(unittest.TestCase):
    def test_read_action_is_executed_logged_and_low_risk(self) -> None:
        proxy = OkProxy()
        forge = ProxyForge(proxy)
        action = forge.execute(
            agent_id="a1",
            principal="bot@acme",
            target_system="github",
            action_type="read_repo",
            resource="acme/x",
        )
        self.assertEqual(action.mode, "read")
        self.assertEqual(action.event_id, "evt-0001")
        self.assertEqual(action.seq, 1)
        self.assertEqual(len(forge.action_log), 1)
        self.assertEqual(proxy.events[0].risk_score, RISK_SCORE[RiskLevel.LOW])

    def test_write_action_carries_high_risk_metadata(self) -> None:
        proxy = OkProxy()
        ProxyForge(proxy).execute(
            agent_id="a1",
            principal="bot@acme",
            target_system="github",
            action_type="push",
            resource="acme/x",
        )
        self.assertEqual(proxy.events[0].risk_score, RISK_SCORE[RiskLevel.HIGH])

    def test_seq_and_event_ids_are_monotonic(self) -> None:
        forge = ProxyForge(OkProxy())
        for resource in ("acme/a", "acme/b", "acme/c"):
            forge.execute(
                agent_id="a1",
                principal="bot@acme",
                target_system="github",
                action_type="read_repo",
                resource=resource,
            )
        log = forge.action_log
        self.assertEqual([a.seq for a in log], [1, 2, 3])
        self.assertEqual([a.event_id for a in log], ["evt-0001", "evt-0002", "evt-0003"])
        self.assertEqual(sorted(a.timestamp for a in log), [a.timestamp for a in log])

    def test_failed_proxy_raises_and_never_records_the_action(self) -> None:
        forge = ProxyForge(FailProxy())
        with self.assertRaises(RuntimeError) as ctx:
            forge.execute(
                agent_id="a1",
                principal="bot@acme",
                target_system="github",
                action_type="push",
                resource="acme/x",
            )
        self.assertIn("lab server unreachable", str(ctx.exception))
        self.assertEqual(forge.action_log, [])

    def test_action_log_is_a_copy(self) -> None:
        forge = ProxyForge(OkProxy())
        forge.execute(
            agent_id="a1",
            principal="bot@acme",
            target_system="github",
            action_type="read_repo",
            resource="acme/x",
        )
        forge.action_log.clear()
        self.assertEqual(len(forge.action_log), 1)


class TestForgeForAgent(unittest.TestCase):
    def test_agent_without_server_gets_the_in_memory_lab_forge(self) -> None:
        self.assertIsInstance(forge_for_agent({"id": "a1"}, []), LabForge)

    def test_agent_with_empty_server_gets_the_in_memory_lab_forge(self) -> None:
        self.assertIsInstance(forge_for_agent({"id": "a1", "server": ""}, []), LabForge)

    def test_agent_bound_to_mock_local_server_gets_a_proxy_forge(self) -> None:
        servers = [{"id": "srv1", "mode": "mock_local", "port": 9001}]
        forge = forge_for_agent({"id": "a1", "server": "srv1"}, servers)
        self.assertIsInstance(forge, ProxyForge)

    def test_dangling_server_reference_is_an_error_not_a_fallback(self) -> None:
        with self.assertRaises(ValueError):
            forge_for_agent({"id": "a1", "server": "ghost"}, [])

    def test_lab_path_with_gateway_gets_a_governed_forge(self) -> None:
        forge = forge_for_agent({"id": "a1"}, [], gateway=FakeGateway())
        self.assertIsInstance(forge, GatewayForge)

    def test_mock_local_on_lab_port_with_gateway_is_governed(self) -> None:
        # A mock_local server on the canonical lab port (8082) resolves to the
        # same target the gateway mediates, so it is governed through it (I2):
        # the campaign lights up /live and /flux. Without a gateway it stays the
        # direct ProxyForge (unit/offline path).
        servers = [{"id": "gh-mock", "mode": "mock_local", "port": 8082}]
        agent = {"id": "a1", "server": "gh-mock"}
        self.assertIsInstance(forge_for_agent(agent, servers), ProxyForge)
        self.assertIsInstance(forge_for_agent(agent, servers, gateway=FakeGateway()), GatewayForge)

    def test_mock_local_off_lab_port_stays_a_proxy_forge(self) -> None:
        # A mock_local server on a non-lab port is NOT the gateway's target;
        # governing it through the lab proxy would hit the wrong host, so it
        # keeps the direct ProxyForge even when a gateway is available (I5).
        servers = [{"id": "other", "mode": "mock_local", "port": 9001}]
        agent = {"id": "a1", "server": "other"}
        self.assertIsInstance(forge_for_agent(agent, servers, gateway=FakeGateway()), ProxyForge)


class FakeGateway:
    """In-test double for the Gateway: captures every submitted ActionRequest
    and returns a configurable verdict, so the GatewayForge contract can be
    asserted without standing up the whole Control Plane (tests/ fixture, R4)."""

    def __init__(self, verdict: str = "allow") -> None:
        self.submitted: list[object] = []
        self._verdict = verdict

    def submit(self, request: object) -> ActionOutcome:
        self.submitted.append(request)
        return ActionOutcome(
            event_id=f"gw-{len(self.submitted)}",
            verdict=self._verdict,
            approval_state="none",
            risk_level=str(RiskLevel.LOW),
            policy_version="v0",
            rule_id=None,
            executed=self._verdict == "allow",
            result=None,
            side_effect_hash=None,
        )


class TestGatewayForge(unittest.TestCase):
    def test_every_action_is_submitted_through_the_gateway(self) -> None:
        gw = FakeGateway()
        forge = GatewayForge(gw)
        forge.execute(
            agent_id="bot",
            principal="bot@corp",
            target_system="github",
            action_type="read_repo",
            resource="acme/x",
        )
        forge.execute(
            agent_id="bot",
            principal="bot@corp",
            target_system="github",
            action_type="open_pr",
            resource="acme/x",
        )
        self.assertEqual(len(gw.submitted), 2)
        self.assertEqual([r.action_type for r in gw.submitted], ["read_repo", "open_pr"])

    def test_action_log_is_labforge_shaped_and_deterministic(self) -> None:
        # Local evt ids + a LogicalClock timestamp, identical to LabForge, so a
        # governed run records and replays byte-stably regardless of the audit
        # store's monotonic ids (I4).
        a = GatewayForge(FakeGateway()).execute(
            agent_id="bot",
            principal="bot@corp",
            target_system="github",
            action_type="read_repo",
            resource="acme/x",
        )
        b = LabForge().execute(
            agent_id="bot",
            principal="bot@corp",
            target_system="github",
            action_type="read_repo",
            resource="acme/x",
        )
        self.assertEqual(a.event_id, b.event_id)
        self.assertEqual(a.event_id, "evt-0001")
        self.assertEqual(a.timestamp, b.timestamp)
        self.assertEqual(a.mode, b.mode)

    def test_deny_verdict_does_not_stop_the_run(self) -> None:
        # Bench semantics: a denied action is still submitted (governed +
        # audited) and still recorded; the forge never raises, so the campaign
        # continues to its next step.
        forge = GatewayForge(FakeGateway(verdict="deny"))
        action = forge.execute(
            agent_id="bot",
            principal="bot@corp",
            target_system="finance",
            action_type="wire_transfer",
            resource="acct/99",
        )
        self.assertEqual(len(forge.action_log), 1)
        self.assertEqual(action.action_type, "wire_transfer")


class FakeConfigStore:
    """In-test double for ConfigStore (tests/ fixture, R4)."""

    def __init__(self, agents: dict[str, dict], backends: dict[str, dict] | None = None) -> None:
        self._agents = agents
        self._backends = backends or {}
        self.servers: list[dict] = []

    def get_agent(self, agent_id: str) -> dict | None:
        return self._agents.get(agent_id)

    def get_ai_backend(self, backend_id: str) -> dict | None:
        return self._backends.get(backend_id)

    def list_servers(self) -> list[dict]:
        return list(self.servers)

    def containment_enabled(self) -> bool:
        # Mirror the real ConfigStore public interface; these runner tests
        # exercise the realism-only path (containment off).
        return False


class FakeRecordingStore:
    def __init__(self) -> None:
        self.saved: dict[str, object] = {}

    def save(self, recording_id: str, recording: object) -> None:
        self.saved[recording_id] = recording


def _mock_agent(agent_id: str, **overrides: object) -> dict:
    agent: dict = {
        "id": agent_id,
        "runtime": "lab",
        "ai_mode": "mock",
        "principal": "bot@acme",
        "target_system": "github",
        "goal": "Inventory repositories",
        "capability_scope": ["read_repo"],
        "scenario": READ_THEN_FINAL,
    }
    agent.update(overrides)
    return agent


def _run_campaign(
    campaign: dict, store: FakeConfigStore
) -> tuple[list[tuple[str, dict]], FakeRecordingStore]:
    recordings = FakeRecordingStore()
    frames: list[tuple[str, dict]] = []
    runner = make_campaign_runner(campaign, store, recordings)
    runner({}, lambda kind, data: frames.append((kind, data)), lambda: False)
    return frames, recordings


def _frames_of(frames: list[tuple[str, dict]], kind: str) -> list[dict]:
    return [data for k, data in frames if k == kind]


class TestCampaignRunner(unittest.TestCase):
    def test_nominal_step_runs_and_persists_one_recording(self) -> None:
        store = FakeConfigStore({"a1": _mock_agent("a1")})
        campaign = {"id": "camp", "steps": [{"agent_id": "a1"}]}
        frames, recordings = _run_campaign(campaign, store)
        self.assertEqual(len(_frames_of(frames, "agent_start")), 1)
        done = _frames_of(frames, "agent_done")
        self.assertEqual(len(done), 1)
        self.assertEqual(done[0]["recording_id"], "camp.00.a1")
        self.assertEqual(done[0]["actions"], 1)
        self.assertIn("camp.00.a1", recordings.saved)
        self.assertEqual(_frames_of(frames, "campaign_done"), [{"campaign_id": "camp", "steps": 1}])

    def test_unknown_agent_is_a_step_error_not_a_crash(self) -> None:
        frames, recordings = _run_campaign(
            {"id": "camp", "steps": [{"agent_id": "ghost"}]}, FakeConfigStore({})
        )
        errors = _frames_of(frames, "step_error")
        self.assertEqual(errors, [{"index": 0, "agent_id": "ghost", "message": "unknown agent"}])
        self.assertEqual(recordings.saved, {})
        self.assertEqual(len(_frames_of(frames, "campaign_done")), 1)

    def test_agent_missing_required_fields_is_a_step_error(self) -> None:
        agent = _mock_agent("a1")
        del agent["goal"]
        frames, _ = _run_campaign(
            {"id": "camp", "steps": [{"agent_id": "a1"}]}, FakeConfigStore({"a1": agent})
        )
        errors = _frames_of(frames, "step_error")
        self.assertEqual(len(errors), 1)
        self.assertIn("goal", errors[0]["message"])

    def test_mock_agent_without_scenario_is_a_step_error(self) -> None:
        agent = _mock_agent("a1")
        del agent["scenario"]
        frames, _ = _run_campaign(
            {"id": "camp", "steps": [{"agent_id": "a1"}]}, FakeConfigStore({"a1": agent})
        )
        errors = _frames_of(frames, "step_error")
        self.assertEqual(len(errors), 1)
        self.assertIn("no scenario", errors[0]["message"])

    def test_real_agent_without_ai_backend_is_a_step_error(self) -> None:
        agent = _mock_agent("a1", ai_mode="real")
        del agent["scenario"]
        frames, _ = _run_campaign(
            {"id": "camp", "steps": [{"agent_id": "a1"}]}, FakeConfigStore({"a1": agent})
        )
        errors = _frames_of(frames, "step_error")
        self.assertEqual(len(errors), 1)
        self.assertIn("no ai_backend bound", errors[0]["message"])

    def test_dangling_server_fails_the_step_and_the_campaign_continues(self) -> None:
        store = FakeConfigStore(
            {"bad": _mock_agent("bad", server="ghost"), "good": _mock_agent("good")}
        )
        campaign = {"id": "camp", "steps": [{"agent_id": "bad"}, {"agent_id": "good"}]}
        frames, recordings = _run_campaign(campaign, store)
        errors = _frames_of(frames, "step_error")
        self.assertEqual(len(errors), 1)
        self.assertIn("ghost", errors[0]["message"])
        self.assertEqual(list(recordings.saved), ["camp.01.good"])

    def test_step_stub_script_overrides_the_agent_scenario(self) -> None:
        agent = _mock_agent("a1", capability_scope=["read_repo", "list_repos"])
        script = [
            {"kind": "tool_call", "tool_name": "list_repos", "tool_args": {"resource": "acme"}},
            {"kind": "final", "text": "done"},
        ]
        store = FakeConfigStore({"a1": agent})
        campaign = {"id": "camp", "steps": [{"agent_id": "a1", "stub_script": script}]}
        frames, _ = _run_campaign(campaign, store)
        steps = _frames_of(frames, "step")
        self.assertEqual([s["action"]["action_type"] for s in steps if s["action"]], ["list_repos"])

    def test_should_stop_halts_before_any_step(self) -> None:
        store = FakeConfigStore({"a1": _mock_agent("a1")})
        campaign = {"id": "camp", "steps": [{"agent_id": "a1"}]}
        runner = make_campaign_runner(campaign, store, FakeRecordingStore())
        frames: list[tuple[str, dict]] = []
        runner({}, lambda kind, data: frames.append((kind, data)), lambda: True)
        self.assertEqual(frames, [])


class TestLaneBRunner(unittest.TestCase):
    def test_result_frame_carries_actions_and_recording(self) -> None:
        agent = _mock_agent("a1")
        frames: list[tuple[str, dict]] = []
        runner = make_lane_b_runner(agent, build_stub_llm(READ_THEN_FINAL))
        runner({}, lambda kind, data: frames.append((kind, data)), lambda: False)
        results = _frames_of(frames, "result")
        self.assertEqual(len(results), 1)
        self.assertEqual(len(results[0]["actions"]), 1)
        self.assertEqual(results[0]["actions"][0]["action_type"], "read_repo")
        self.assertIn("steps", results[0]["recording"])

    def test_step_frame_carries_the_decision_next_to_the_action(self) -> None:
        # F2: the step frame pairs the LLM decision with the executed action so
        # the console can show why each side effect happened.
        agent = _mock_agent("a1")
        frames: list[tuple[str, dict]] = []
        runner = make_lane_b_runner(agent, build_stub_llm(READ_THEN_FINAL))
        runner({}, lambda kind, data: frames.append((kind, data)), lambda: False)
        steps = _frames_of(frames, "step")
        self.assertTrue(steps)
        first = steps[0]
        self.assertEqual(first["decision"]["tool_name"], "read_repo")
        self.assertEqual(first["action"]["action_type"], "read_repo")

    def test_lane_b_runner_paces_when_pace_set(self) -> None:
        # Pacing wires through the dashboard runner: the agent carries a
        # pace_ms, so the wrapped on_step sleeps AFTER each step. The agent has
        # no server binding, so it runs the in-memory LabForge path (no HTTP,
        # deterministic). We assert time.sleep was called at least once (proves
        # on_step was paced); with no pace it must NOT sleep (pass-through).
        sleeps: list[float] = []
        original_sleep = runners_mod.time.sleep
        runners_mod.time.sleep = lambda seconds: sleeps.append(seconds)
        try:
            agent = _mock_agent("a1", pace_ms=200)
            runner = make_lane_b_runner(agent, build_stub_llm(READ_THEN_FINAL))
            runner({}, lambda kind, data: None, lambda: False)
            self.assertTrue(sleeps, "expected time.sleep to be called (pace not wired)")

            # No pace set -> no sleep (transparent pass-through).
            sleeps.clear()
            unpaced = make_lane_b_runner(_mock_agent("a1"), build_stub_llm(READ_THEN_FINAL))
            unpaced({}, lambda kind, data: None, lambda: False)
            self.assertEqual(sleeps, [], "expected no sleep when pace is unset")
        finally:
            runners_mod.time.sleep = original_sleep


class TestReplayRunner(unittest.TestCase):
    def test_replay_of_a_recording_matches_the_original(self) -> None:
        result = run_agent(
            agent_id="a1",
            principal="bot@acme",
            target_system="github",
            goal="Inventory repositories",
            capability_scope=["read_repo"],
            llm=build_stub_llm(READ_THEN_FINAL),
        )
        frames: list[tuple[str, dict]] = []
        runner = make_replay_runner(result.recording, "rec-1")
        runner({}, lambda kind, data: frames.append((kind, data)), lambda: False)
        replays = _frames_of(frames, "replay_result")
        self.assertEqual(len(replays), 1)
        self.assertTrue(replays[0]["matches_original"])
        self.assertEqual(replays[0]["recording_id"], "rec-1")
        self.assertEqual(replays[0]["actions"], [a.to_dict() for a in result.actions])


class TestBuildStubLlm(unittest.TestCase):
    def test_maps_script_dicts_to_decisions_with_defaults(self) -> None:
        llm = build_stub_llm(
            [
                {"kind": "tool_call", "tool_name": "read_repo"},
                {"kind": "final"},
            ]
        )
        self.assertIsInstance(llm, StubLlm)
        first = llm.decide(system="s", history=[], tools=[])
        self.assertEqual(
            first, LlmDecision(kind="tool_call", tool_name="read_repo", tool_args={}, text="")
        )
        second = llm.decide(system="s", history=[], tools=[])
        self.assertEqual(second.kind, "final")
        self.assertEqual(second.text, "")


if __name__ == "__main__":
    unittest.main()
