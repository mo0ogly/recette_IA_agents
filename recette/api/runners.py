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
from ..events import AgentAction, LogicalClock, Mode, mode_for_action
from ..forge import GitForge, LabForge
from ..harness import discover_agent_dirs
from ..harness import run_agent as run_ident_agent
from ..lane_b import run_agent as run_lane_b_agent
from ..llm import LlmBackend, LlmDecision, StubLlm
from ..platform.catalog.model import RISK_SCORE, RiskLevel
from ..platform.events import PlatformActionEvent
from ..platform.proxy.lab_proxy import LabHttpProxy
from ..platform.proxy.protocol import ExternalSystemProxy
from ..platform.proxy.router import resolve_proxy
from ..platform.proxy.tracing import TraceRecorder, TracingProxy
from ..recording import Recording, replay_backend
from ..scorecard import Scorecard

Emit = Callable[[str, dict], None]
ShouldStop = Callable[[], bool]


class ProxyForge:
    """GitForge adapter that executes every action through an ExternalSystemProxy (I5).

    Used when an agent is bound to a server entry: each tool call becomes a
    PlatformActionEvent shipped over the lab wire format to the agent's
    server. event_id/timestamp are derived from a sequence + LogicalClock
    (deterministic, I4). risk fields are transport metadata only here --
    governance risk scoring stays in the gateway decision path.

    Failure mode (fail-safe): a transport error or non-success envelope
    raises RuntimeError, which fails the run. The action is never recorded
    as executed and execution never silently falls back to another target.
    """

    def __init__(self, proxy: ExternalSystemProxy, clock: LogicalClock | None = None) -> None:
        self._proxy = proxy
        self._clock = clock or LogicalClock()
        self._log: list[AgentAction] = []
        self._seq = 0

    def execute(
        self,
        *,
        agent_id: str,
        principal: str,
        target_system: str,
        action_type: str,
        resource: str,
        approved: bool = False,
        params: dict | None = None,
    ) -> AgentAction:
        self._seq += 1
        timestamp = self._clock.tick()
        mode = mode_for_action(action_type)
        risk_level = RiskLevel.LOW if mode is Mode.READ else RiskLevel.HIGH
        event = PlatformActionEvent(
            event_id=f"evt-{self._seq:04d}",
            timestamp=timestamp,
            agent_id=agent_id,
            capability_scope=(),  # scope enforcement lives in the tool registry/gateway
            role="",
            action_type=action_type,
            target_system=target_system,
            resource=resource,
            payload=dict(params or {}),
            risk_score=RISK_SCORE[risk_level],
            risk_level=str(risk_level),
        )
        result = self._proxy.execute(event)
        if not result.ok:
            raise RuntimeError(
                f"proxy execution failed for {action_type} on {resource!r}: "
                f"{result.error or f'HTTP {result.status_code}'}"
            )
        action = AgentAction(
            event_id=event.event_id,
            seq=self._seq,
            timestamp=timestamp,
            agent_id=agent_id,
            principal=principal,
            target_system=target_system,
            action_type=action_type,
            mode=mode.value,
            resource=resource,
            approved=approved,
            params=dict(params or {}),
        )
        self._log.append(action)
        return action

    @property
    def action_log(self) -> list[AgentAction]:
        return list(self._log)


def forge_for_agent(
    agent_cfg: dict,
    servers: list[dict],
    default_proxy: ExternalSystemProxy | None = None,
    *,
    recorder: TraceRecorder | None = None,
    debug_enabled: bool = False,
) -> GitForge:
    """Forge for one run. An agent without a ``server`` binding keeps the
    historical in-memory LabForge; an agent bound to a server executes
    through the proxy resolved from the server registry (I5).

    When ``recorder`` is provided, the proxy-bound path is wrapped in a
    ``TracingProxy`` so each side effect a real agent produces is recorded for
    the debug console (parametrable via ``debug_enabled``). The in-memory
    LabForge path produces no external side effect, so it is not traced.

    Raises ValueError on a dangling or unsupported server reference
    (fail-safe: the run must fail, never execute against the wrong target).
    """
    if not agent_cfg.get("server"):
        return LabForge()
    # The default is never returned here (the agent has a server), but
    # resolve_proxy's contract requires the actual default proxy.
    proxy = resolve_proxy(agent_cfg, servers, default_proxy or LabHttpProxy())
    if recorder is not None:
        proxy = TracingProxy(proxy, recorder, enabled=debug_enabled)
    return ProxyForge(proxy)


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
    agent_cfg: dict,
    llm: LlmBackend,
    *,
    config_store: object | None = None,
    recorder: TraceRecorder | None = None,
    debug_enabled: bool = False,
) -> Callable[[dict, Emit, ShouldStop], None]:
    def runner(params: dict, emit: Emit, should_stop: ShouldStop) -> None:
        # Proxy resolution happens inside the runner so a dangling server
        # reference surfaces as an explicit run failure (status=failed +
        # error frame via RunManager), never as an API crash and never as
        # a silent fallback to the wrong execution target (I5 fail-safe).
        servers = config_store.list_servers() if config_store is not None else []  # type: ignore[attr-defined]
        forge = forge_for_agent(
            agent_cfg, servers, recorder=recorder, debug_enabled=debug_enabled
        )
        result = run_lane_b_agent(
            agent_id=agent_cfg["id"],
            principal=agent_cfg["principal"],
            target_system=agent_cfg["target_system"],
            goal=agent_cfg["goal"],
            capability_scope=agent_cfg["capability_scope"],
            llm=llm,
            forge=forge,
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
    campaign: dict,
    config_store: object,
    recording_store: object,
    secret_store: object | None = None,
    *,
    recorder: TraceRecorder | None = None,
    debug_enabled: bool = False,
) -> Callable[[dict, Emit, ShouldStop], None]:
    """Run each campaign step as a Lane B agent, persisting one recording per
    step. A step with a stub_script runs as a mock; otherwise the agent's bound
    ai_backend drives a live LLM. Key resolution (R8): the per-backend secret
    store first, then the provider's env fallback. The key is never logged."""
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
                k
                for k in ("principal", "target_system", "goal", "capability_scope")
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
            # A step can override the script; otherwise a mock agent runs its
            # stored scenario, and a real-AI agent uses its bound ai_backend.
            stub = step.get("stub_script")
            if stub is None and agent_cfg.get("ai_mode", "mock") != "real":
                stub = agent_cfg.get("scenario")
            if stub:
                llm: LlmBackend = build_stub_llm(stub)
            elif agent_cfg.get("ai_mode", "mock") != "real":
                emit(
                    "step_error",
                    {"index": idx, "agent_id": agent_id, "message": "mock agent has no scenario"},
                )
                continue
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
                # Per-backend secret first, then env fallback (R8). base_url
                # only matters for openai_compat. The key is never logged.
                api_key = (
                    secret_store.get_secret(agent_cfg.get("ai_backend_id", ""))  # type: ignore[attr-defined]
                    if secret_store is not None
                    else None
                )
                llm = build_llm(
                    provider, model, base_url=backend.get("base_url"), api_key=api_key
                )
            try:
                # Per-agent proxy routing (I5): a dangling server reference
                # fails this step explicitly, never falls back to the default.
                forge = forge_for_agent(
                    agent_cfg,
                    config_store.list_servers(),  # type: ignore[attr-defined]
                    recorder=recorder,
                    debug_enabled=debug_enabled,
                )
            except ValueError as exc:
                emit("step_error", {"index": idx, "agent_id": agent_id, "message": str(exc)})
                continue
            emit("agent_start", {"index": idx, "agent_id": agent_id, "provider": provider})
            result = run_lane_b_agent(
                agent_id=agent_cfg["id"],
                principal=agent_cfg["principal"],
                target_system=agent_cfg["target_system"],
                goal=agent_cfg["goal"],
                capability_scope=agent_cfg["capability_scope"],
                llm=llm,
                forge=forge,
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
