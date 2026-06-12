"""U1 run bodies — thin wrappers that reuse recette and emit event frames.

A runner has signature runner(params, emit, should_stop) -> None, where
emit(type: str, data: dict) records one frame and should_stop() -> bool is cooperative.
Runners never touch HTTP or asyncio — they are pure orchestration over recette.
"""

from __future__ import annotations

from collections.abc import Callable

from ..adapters import ReferenceDiscoveryAdapter, ReferenceIdentificationAdapter
from ..discovery_harness import (
    SURFACE_CORPUS,
    SURFACE_ORDER,
    discover_repo_dirs,
    run_discovery_recette,
)
from ..harness import discover_agent_dirs
from ..harness import run_agent as run_ident_agent
from ..lane_b import run_agent as run_lane_b_agent
from ..llm import LlmBackend, LlmDecision, StubLlm
from ..recording import Recording, replay_backend
from ..scorecard import Scorecard

Emit = Callable[[str, dict], None]
ShouldStop = Callable[[], bool]


def _scope_from_recording(recording: Recording) -> list[str]:
    """Derive the capability scope from a recording's tool calls so a replay is
    self-contained (the recording does not carry the original scope)."""
    return sorted(
        {
            s.decision.tool_name
            for s in recording.steps
            if s.decision.is_tool_call and s.decision.tool_name
        }
    )


def make_lane_b_runner(
    agent_cfg: dict, llm: LlmBackend
) -> Callable[[dict, Emit, ShouldStop], None]:
    def runner(params: dict, emit: Emit, should_stop: ShouldStop) -> None:
        result = run_lane_b_agent(
            agent_id=agent_cfg["id"],
            principal=agent_cfg["principal"],
            target_system=agent_cfg["target_system"],
            goal=agent_cfg["goal"],
            capability_scope=agent_cfg["capability_scope"],
            llm=llm,
            on_step=lambda i, step: emit("step", {"index": i, "action": step.action}),
            should_stop=should_stop,
        )
        emit(
            "result",
            {
                "actions": [a.to_dict() for a in result.actions],
                "recording": result.recording.to_dict(),
            },
        )

    return runner


def _lane_b_step_emit(emit: Emit, agent_id: str) -> Callable[[int, object], None]:
    def on_step(i: int, step: object) -> None:
        action = getattr(step, "action", None)
        emit("step", {"agent_id": agent_id, "index": i, "action": action})

    return on_step


def make_campaign_runner(
    campaign: dict, config_store: object, recording_store: object
) -> Callable[[dict, Emit, ShouldStop], None]:
    """Run each campaign step as a Lane B agent, persisting one recording per
    step. A step with a stub_script runs as a mock; otherwise the agent's bound
    ai_backend drives a live LLM (key from env, R8)."""
    from ..llm import build_llm

    def runner(params: dict, emit: Emit, should_stop: ShouldStop) -> None:
        steps = campaign.get("steps", [])
        for idx, step in enumerate(steps):
            if should_stop():
                return
            agent_id = step.get("agent_id", "")
            agent_cfg = config_store.get_agent(agent_id)  # type: ignore[attr-defined]
            if agent_cfg is None:
                emit("step_error", {"index": idx, "agent_id": agent_id, "message": "unknown agent"})
                continue
            missing = [
                k for k in ("principal", "target_system", "goal", "capability_scope")
                if not agent_cfg.get(k)
            ]
            if missing:
                emit(
                    "step_error",
                    {"index": idx, "agent_id": agent_id, "message": f"agent missing {missing}"},
                )
                continue
            provider = "stub"
            model = ""
            if step.get("stub_script") is not None:
                llm: LlmBackend = build_stub_llm(step["stub_script"])
            else:
                backend = config_store.get_ai_backend(agent_cfg.get("ai_backend_id", ""))  # type: ignore[attr-defined]
                if backend is None:
                    emit(
                        "step_error",
                        {"index": idx, "agent_id": agent_id, "message": "no ai_backend bound"},
                    )
                    continue
                provider = backend["provider"]
                model = backend["model"]
                llm = build_llm(provider, model)  # live; key from env (R8)
            emit("agent_start", {"index": idx, "agent_id": agent_id, "provider": provider})
            result = run_lane_b_agent(
                agent_id=agent_cfg["id"],
                principal=agent_cfg["principal"],
                target_system=agent_cfg["target_system"],
                goal=agent_cfg["goal"],
                capability_scope=agent_cfg["capability_scope"],
                llm=llm,
                provider=provider,
                model=model,
                on_step=_lane_b_step_emit(emit, agent_id),
                should_stop=should_stop,
            )
            rec_id = f"{campaign['id']}.{idx:02d}.{agent_id}"
            recording_store.save(rec_id, result.recording)  # type: ignore[attr-defined]
            emit(
                "agent_done",
                {
                    "index": idx,
                    "agent_id": agent_id,
                    "actions": len(result.actions),
                    "recording_id": rec_id,
                },
            )
        emit("campaign_done", {"campaign_id": campaign["id"], "steps": len(steps)})

    return runner


def make_replay_runner(
    recording: Recording, recording_id: str
) -> Callable[[dict, Emit, ShouldStop], None]:
    """Deterministically replay a recording (I4): re-issue its decisions and
    compare the resulting action log to the original."""

    def runner(params: dict, emit: Emit, should_stop: ShouldStop) -> None:
        result = run_lane_b_agent(
            agent_id=recording.agent_id,
            principal=recording.principal,
            target_system=recording.target_system,
            goal=recording.goal,
            capability_scope=_scope_from_recording(recording),
            llm=replay_backend(recording),
            provider="replay",
            on_step=_lane_b_step_emit(emit, recording.agent_id),
            should_stop=should_stop,
        )
        replayed = [a.to_dict() for a in result.actions]
        emit(
            "replay_result",
            {
                "recording_id": recording_id,
                "actions": replayed,
                "matches_original": replayed == recording.actions(),
            },
        )

    return runner


def build_stub_llm(script: list[dict]) -> StubLlm:
    return StubLlm(
        [
            LlmDecision(
                kind=d["kind"],
                tool_name=d.get("tool_name"),
                tool_args=d.get("tool_args", {}) or {},
                text=d.get("text", ""),
            )
            for d in script
        ]
    )


def identification_runner(params: dict, emit: Emit, should_stop: ShouldStop) -> None:
    disc = ReferenceDiscoveryAdapter()
    ident = ReferenceIdentificationAdapter()
    scorecard = Scorecard()
    for d in discover_agent_dirs():
        if should_stop():
            return
        result = run_ident_agent(d, discovery=disc, identification=ident)
        scorecard.add(result)
        emit(
            "agent_result",
            {
                "agent_id": result.agent_id,
                "passed": result.passed,
                "predicted_verdict": result.predicted_verdict,
                "expected_verdict": result.expected_verdict,
            },
        )
    emit("scorecard", _scorecard_data(scorecard))


def discovery_runner(params: dict, emit: Emit, should_stop: ShouldStop) -> None:
    surface = params.get("surface", "all")
    surfaces = (
        [s for s in SURFACE_ORDER if discover_repo_dirs(SURFACE_CORPUS[s])]
        if surface == "all"
        else [surface]
    )
    for s in surfaces:
        if should_stop():
            return
        sc = run_discovery_recette(corpus_root=SURFACE_CORPUS[s])
        emit(
            "scorecard",
            {
                "surface": s,
                "total": sc.total,
                "passed": sc.passed_count,
                "false_positives": sc.false_positives,
                "false_negatives": sc.false_negatives,
                "all_passed": sc.all_passed,
            },
        )


def _scorecard_data(sc: Scorecard) -> dict:
    return {
        "total": sc.total,
        "passed": sc.passed_count,
        "false_positives": sc.false_positives,
        "false_negatives": sc.false_negatives,
        "detection_rate": sc.detection_rate,
        "all_passed": sc.all_passed,
    }
