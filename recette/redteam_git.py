"""Deterministic git red-team recette: drive a Lane B goal-driven run, re-judge, compare.

Loads a git-sim-scenario, derives the Lane B ``run_agent`` arguments from the git
``target_manifest`` exactly as ``make_lane_b_runner`` does (agent_id, principal,
target_system, capability_scope as tool-name strings), drives the decide->act loop
with a ReplayLlm subject program (I4) plus an optional adversarial forge
``tool_injection`` (AgentDojo injection-via-tool-output), judges the resulting
AgentAction log with ``judge_subject`` (the git identification judge), and reports
whether the recette caught (or correctly cleared) the attacked agent.

Pure + deterministic: no clock, no random, no network -- a LabForge executes the
side effects in memory and a ReplayLlm replays the scripted decisions. The
``anomaly_caught`` flag is the recette's true-positive/true-negative result: the
predicted verdict matches the scenario's expected verdict.
"""

from __future__ import annotations

from collections.abc import Callable

from .events import AgentAction
from .judge import judge_subject
from .lane_b import _result_text, run_agent
from .llm import LlmDecision, ReplayLlm
from .manifest import validate
from .redteam_recette import ScenarioOutcome, _violation_of


def _run_args(manifest: dict) -> dict:
    """Derive Lane B run_agent args from a git manifest, mirroring how
    make_lane_b_runner derives them from a config agent: agent_id, principal
    (the declared identity), the first declared target_system, and the
    capability_scope flattened to the list of tool-name strings build_tools
    expects (the git capability_scope is a list of {action, mode, resources}).

    Fail-safe (legibility-first): an empty target_systems raises a clear
    ValueError naming the offending agent rather than a bare IndexError."""
    targets = manifest.get("target_systems") or []
    if not targets:
        raise ValueError(
            f"git scenario manifest {manifest.get('agent_id')!r} has no target_systems"
        )
    return {
        "agent_id": manifest["agent_id"],
        "principal": manifest["declared_identity"]["principal"],
        "target_system": targets[0],
        "capability_scope": [c["action"] for c in manifest["capability_scope"]],
    }


def _replay_program(subject_program: list[dict]) -> ReplayLlm:
    """A ReplayLlm replaying each git tool-call step, then a terminal final so
    the Lane B loop ends deterministically."""
    decisions = [
        LlmDecision(
            kind="tool_call",
            tool_name=step["tool_name"],
            tool_args=dict(step.get("tool_args", {}) or {}),
        )
        for step in subject_program
    ]
    decisions.append(LlmDecision(kind="final", text="done"))
    return ReplayLlm(decisions)


def _tool_output(injection: list[str] | None) -> Callable[[AgentAction], str]:
    """Build the tool-result callback. Without injection, the canonical ok: text.
    With injection, the Nth executed action gets injection[N] (adversarial forge
    output); an out-of-range index falls back to the default ok: text. The
    callback is a pure closure over an index list -- no clock/random (I4)."""
    if not injection:
        return _result_text
    state = {"n": 0}

    def output(action: AgentAction) -> str:
        i = state["n"]
        state["n"] = i + 1
        if 0 <= i < len(injection):
            return injection[i]
        return _result_text(action)

    return output


def _outcome(scenario: dict, verdict, vt: str | None) -> ScenarioOutcome:
    expected = scenario["expected"]
    return ScenarioOutcome(
        scenario_id=scenario["scenario_id"],
        verdict=verdict.verdict,
        expected_verdict=expected["verdict"],
        violation_type=vt,
        anomaly_caught=verdict.verdict == expected["verdict"],
        tags=dict(scenario.get("tags", {})),
    )


def _judge_once(scenario: dict, manifest: dict):
    """Run the Lane B goal-driven loop once and judge the action log. Returns
    (result, verdict). Pure + deterministic (LabForge + ReplayLlm)."""
    args = _run_args(manifest)
    result = run_agent(
        agent_id=args["agent_id"],
        principal=args["principal"],
        target_system=args["target_system"],
        goal=scenario["goal"],
        capability_scope=args["capability_scope"],
        llm=_replay_program(scenario["subject_program"]),
        tool_output=_tool_output(scenario.get("tool_injection")),
    )
    verdict = judge_subject(manifest, result.actions)
    return result, verdict


def _validate(scenario: dict) -> dict:
    """Validate the scenario and its embedded target_manifest. Returns the
    manifest. Raises ValueError on either invalid (fail-safe)."""
    errors = validate("git_sim_scenario", scenario)
    if errors:
        raise ValueError(f"invalid git scenario: {errors}")
    manifest = scenario["target_manifest"]
    manifest_errors = validate("manifest", manifest)
    if manifest_errors:
        raise ValueError(f"invalid target_manifest: {manifest_errors}")
    return manifest


def run_git_scenario(scenario: dict) -> ScenarioOutcome:
    """Drive a git red-team scenario through the Lane B goal-driven loop and
    report whether the recette caught the agent.

    Validates the scenario and its embedded target_manifest, replays the subject
    program (with optional adversarial tool_injection) through run_agent, judges
    the resulting AgentAction log with judge_subject (git identification judge),
    and returns a ScenarioOutcome whose anomaly_caught flag is True when the
    predicted verdict matches the scenario's expected verdict.

    I4 self-check: the run is executed twice and the two ScenarioOutcomes must be
    byte-identical; a frozen scenario that does not replay to the recorded verdict
    raises ValueError. Raises ValueError if the scenario or target_manifest is
    invalid.
    """
    manifest = _validate(scenario)
    _, verdict_a = _judge_once(scenario, manifest)
    outcome_a = _outcome(scenario, verdict_a, _violation_of(verdict_a))
    _, verdict_b = _judge_once(scenario, manifest)
    outcome_b = _outcome(scenario, verdict_b, _violation_of(verdict_b))
    if outcome_a != outcome_b:
        raise ValueError(
            f"non-deterministic git scenario {scenario['scenario_id']!r}: "
            f"{outcome_a} != {outcome_b}"
        )
    return outcome_a


def run_git_scenario_view(scenario: dict) -> dict:
    """Drive a git red-team scenario and return its outcome fields PLUS the
    action log, for the console / promote path (mirrors run_scenario_view).

    Returns the ScenarioOutcome fields (scenario_id, verdict, expected_verdict,
    violation_type, anomaly_caught, tags), the human ``name``, the ``goal``, and
    the ordered ``actions`` (the git side effects the subject produced) so the
    console can step through what the agent did (legibility-first). Pure +
    deterministic (I4); raises ValueError on an invalid scenario.
    """
    manifest = _validate(scenario)
    result, verdict = _judge_once(scenario, manifest)
    expected = scenario["expected"]
    return {
        "scenario_id": scenario["scenario_id"],
        "name": scenario.get("name", scenario["scenario_id"]),
        "goal": scenario["goal"],
        "verdict": verdict.verdict,
        "expected_verdict": expected["verdict"],
        "violation_type": _violation_of(verdict),
        "anomaly_caught": verdict.verdict == expected["verdict"],
        "tags": dict(scenario.get("tags", {})),
        "actions": [a.to_dict() for a in result.actions],
    }
