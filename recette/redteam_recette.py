"""Deterministic red-team recette: replay a scenario, re-judge, compare.

Loads a sim-scenario, drives recette.simulate.simulate() with a ReplayLlm
subject program (I4) and the scripted attack turns, judges the action log with
judge_subject, and reports whether the recette caught (or correctly cleared) the
attacked agent. Pure + deterministic: no clock, no random, no network. The
'anomaly_caught' flag is the recette's true-positive/true-negative result --
the predicted verdict matches the scenario's expected verdict.
"""

from __future__ import annotations

from dataclasses import dataclass

from .judge import judge_subject
from .llm import LlmDecision, ReplayLlm
from .manifest import validate
from .simulate import simulate

_VIOLATION_DIM = {
    "identity_mismatch": "identity_match",
    "capability_overreach": "capabilities_conform",
    "policy_violation": "policy_compliant",
    "behavior_anomaly": "behavior_expected",
}


def _deny(_: object) -> bool:
    """Deny-all approver: an approval-gated tool call is never approved (I6)."""
    return False


# Maps a scenario `approver` name (schema enum) to an Approver callable passed to
# simulate(). Only schema-validated enum values reach this map (an unknown name
# would KeyError, but the scenario is validated first in run_scenario).
_APPROVERS = {"deny_all": _deny}


def _approver_for(name: str):
    """Resolve a scenario approver name to its Approver callable."""
    return _APPROVERS[name]


@dataclass(frozen=True)
class ScenarioOutcome:
    scenario_id: str
    verdict: str  # predicted: "correct" | "incorrect"
    expected_verdict: str
    violation_type: str | None  # derived broken dimension, or None
    anomaly_caught: bool  # predicted == expected
    tags: dict[str, str]


def _program(steps: list[dict]) -> ReplayLlm:
    return ReplayLlm(
        [
            LlmDecision(kind=s["kind"], tool_name=s.get("tool_name"), text=s.get("text", ""))
            for s in steps
        ]
    )


def _violation_of(result) -> str | None:
    broken = [vt for vt, attr in _VIOLATION_DIM.items() if not getattr(result, attr)]
    return broken[0] if broken else None


def _replay(scenario: dict):
    """Validate, replay and judge a scenario. Returns (spec, result, verdict).

    Shared core of run_scenario and run_scenario_view: validates the scenario
    and its embedded target_spec, replays the subject program against the
    scripted attack turns via simulate(), and re-judges the action log with
    judge_subject. Pure + deterministic (I4). Raises ValueError on an invalid
    scenario or target_spec.
    """
    errors = validate("sim_scenario", scenario)
    if errors:
        raise ValueError(f"invalid scenario: {errors}")
    spec = scenario["target_spec"]
    spec_errors = validate("manifest", spec)
    if spec_errors:
        raise ValueError(f"invalid target_spec: {spec_errors}")
    result = simulate(
        spec=spec,
        subject=_program(scenario["subject_program"]),
        user_turns=list(scenario["attack"]["user_turns"]),
        approver=_approver_for(scenario.get("approver", "deny_all")),
    )
    verdict = judge_subject(spec, result.action_log)
    return spec, result, verdict


def run_scenario(scenario: dict) -> ScenarioOutcome:
    """Replay a red-team scenario and report whether the recette caught the agent.

    Validates the scenario and its embedded target_spec, replays the subject
    program against the scripted attack turns via simulate(), re-judges the
    resulting action log with judge_subject, and returns a ScenarioOutcome whose
    anomaly_caught flag is True when the predicted verdict matches the scenario's
    expected verdict (a true positive on an attacked agent, or a true negative on
    a clean one). Raises ValueError if the scenario or target_spec is invalid.
    """
    _, _, verdict = _replay(scenario)
    expected = scenario["expected"]
    return ScenarioOutcome(
        scenario_id=scenario["scenario_id"],
        verdict=verdict.verdict,
        expected_verdict=expected["verdict"],
        violation_type=_violation_of(verdict),
        anomaly_caught=verdict.verdict == expected["verdict"],
        tags=dict(scenario.get("tags", {})),
    )


def run_scenario_view(scenario: dict) -> dict:
    """Replay a scenario and return its outcome fields PLUS the transcript.

    A console-oriented view that keeps all the simulate-wiring in one place: it
    returns the ScenarioOutcome fields (scenario_id, verdict, expected_verdict,
    violation_type, anomaly_caught, tags), the human ``name`` from the scenario
    JSON, and the ``transcript`` (the ordered conversation turns) so the console
    can step through what hijacked the subject (legibility-first). Pure +
    deterministic (I4); raises ValueError on an invalid scenario.
    """
    _, result, verdict = _replay(scenario)
    expected = scenario["expected"]
    return {
        "scenario_id": scenario["scenario_id"],
        "name": scenario.get("name", scenario["scenario_id"]),
        "verdict": verdict.verdict,
        "expected_verdict": expected["verdict"],
        "violation_type": _violation_of(verdict),
        "anomaly_caught": verdict.verdict == expected["verdict"],
        "tags": dict(scenario.get("tags", {})),
        "transcript": [
            {"role": m.role, "content": m.content, "tool_name": m.tool_name}
            for m in result.transcript
        ],
    }
