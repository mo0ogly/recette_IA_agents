"""U1 run bodies — thin wrappers that reuse recette and emit event frames.

A runner has signature runner(params, emit, should_stop) -> None, where
emit(type: str, data: dict) records one frame and should_stop() -> bool is cooperative.
Runners never touch HTTP or asyncio — they are pure orchestration over recette.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TYPE_CHECKING

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
from ..platform.gateway import ActionRequest, Gateway
from ..platform.netname.resolver import ResolutionDenied

if TYPE_CHECKING:
    from ..capture.llm_trace import LlmCallTrace
from ..platform.proxy.lab_proxy import LabHttpProxy, lab_url_from_env
from ..platform.proxy.protocol import ExternalSystemProxy
from ..platform.proxy.router import resolve_proxy
from ..platform.proxy.tracing import TraceRecorder, TracingProxy
from ..recording import Recording, replay_backend
from ..scorecard import Scorecard
from .config_store import ConfigStore
from .run_frames import tool_call_frame

logger = logging.getLogger(__name__)

Emit = Callable[[str, dict], None]
ShouldStop = Callable[[], bool]


def _audit_resolution_denied(gateway: Gateway | None, agent_id: str, exc: ResolutionDenied) -> None:
    """Emit the audited resolution_denied event (fail-safe containment signal).

    The caller has ALREADY been denied a proxy (resolve_proxy raised); the
    denial is enforced by the call-site's own control flow (re-raise or
    step_error + continue) regardless of this function. When a gateway is
    available the deny is appended to the audit sink (I1/I2). When no gateway is
    available the denial is still enforced by the caller; log it so a blocked
    attempt is never invisible (Fix 3 -- no silent unaudited denial)."""
    if gateway is not None:
        gateway.record_resolution_denied(
            agent_id=agent_id, name=exc.name, reason="not_in_allowlist"
        )
    else:
        logger.warning(
            "resolution_denied (unaudited: no gateway): agent=%s name=%s", agent_id, exc.name
        )


# Pacing is operational metadata, never a decision input (I4 / R20): the delay
# lives here in the ops layer, never inside lane_b's pure execution loop.
MAX_PACE_MS = 30000
PACE_SLICE_MS = 100


def resolve_pace(agent_cfg: dict, servers: list[dict]) -> int:
    """Resolve the inter-action delay for an agent: agent ?? server ?? 0.

    Clamped to [0, MAX_PACE_MS]. Any malformed value falls back to 0 (fail-safe
    to instant -- a bad pace never crashes or freezes a run).
    """

    def _coerce(value: object) -> int | None:
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        return value

    pace = _coerce(agent_cfg.get("pace_ms"))
    if pace is None:
        server_id = agent_cfg.get("server")
        server = next((s for s in servers if s.get("id") == server_id), None)
        pace = _coerce(server.get("pace_ms")) if server is not None else None
    if pace is None:
        return 0
    return max(0, min(pace, MAX_PACE_MS))


def _paced_on_step(inner, pace_ms: int, should_stop):
    """Wrap an on_step callback so it sleeps ``pace_ms`` AFTER emitting, in
    PACE_SLICE_MS ticks, bailing as soon as should_stop() is true. At pace 0 it
    is a transparent pass-through (never sleeps)."""
    if pace_ms <= 0:
        return inner

    def wrapped(i: int, step) -> None:
        inner(i, step)
        remaining = pace_ms
        while remaining > 0:
            if should_stop():
                return
            tick = min(PACE_SLICE_MS, remaining)
            time.sleep(tick / 1000)
            remaining -= tick

    return wrapped


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


class GatewayForge:
    """GitForge adapter that submits every action through the Gateway (I2).

    Operator-driven runs (the dashboard "Lancer" and campaign runs) execute the
    lab-mode path. Historically that path used the in-memory LabForge, which is
    invisible to the Control Plane: the action never reaches the policy engine,
    never lands in the append-only audit store, and never reaches the realtime
    transport -- so the /live and /flux views stay blind to it. GatewayForge
    closes that gap: each tool call becomes an ``ActionRequest`` evaluated by the
    gateway (policy allow/deny/escalate), the side effect on allow is mediated by
    the gateway proxy (I5), and the governed event is appended + published, so a
    campaign lights up /live and /flux in real time.

    Bench semantics (operator decision): a DENY or ESCALATE is recorded as a
    governed event but the run CONTINUES -- a single sensitive action never
    stalls the campaign; the verdict picture is exactly what the bench measures.

    Determinism (I4): the recorded action log is byte-identical to LabForge --
    local ``evt-{seq}`` ids and a ``LogicalClock`` timestamp, never the gateway's
    monotonic audit id -- so recordings and replays stay stable regardless of how
    many events already sit in the store. The same logical tick is fed to the
    ``ActionRequest`` so the governed event timestamp is a captured input, not a
    wall-clock read.
    """

    def __init__(self, gateway: Gateway, clock: LogicalClock | None = None) -> None:
        self._gateway = gateway
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
        # Mediated submission: the gateway appends the governed event to the
        # audit store and publishes it to the realtime transport. The outcome
        # (allow/deny/escalate) is intentionally NOT used to gate the recorded
        # action -- record + continue (bench semantics).
        self._gateway.submit(
            ActionRequest(
                agent_id=agent_id,
                action_type=action_type,
                target_system=target_system,
                resource=resource,
                payload=dict(params or {}),
                timestamp=timestamp,
            )
        )
        action = AgentAction(
            event_id=f"evt-{self._seq:04d}",
            seq=self._seq,
            timestamp=timestamp,
            agent_id=agent_id,
            principal=principal,
            target_system=target_system,
            action_type=action_type,
            mode=mode_for_action(action_type).value,
            resource=resource,
            approved=approved,
            params=dict(params or {}),
        )
        self._log.append(action)
        return action

    @property
    def action_log(self) -> list[AgentAction]:
        return list(self._log)


def _lab_port() -> int | None:
    """Port of the canonical lab the gateway mediates (R19/R5). Used to decide
    whether a mock_local server resolves to that same lab, so a governed forge
    executes against the gateway's own target and nothing else."""
    from urllib.parse import urlparse

    try:
        return urlparse(lab_url_from_env()).port
    except ValueError:
        return None


def forge_for_agent(
    agent_cfg: dict,
    servers: list[dict],
    default_proxy: ExternalSystemProxy | None = None,
    *,
    recorder: TraceRecorder | None = None,
    debug_enabled: bool = False,
    run_id: str | None = None,
    gateway: Gateway | None = None,
    wire_proxy_url: str | None = None,
    containment: bool = False,
) -> GitForge:
    """Forge for one run. An agent without a ``server`` binding takes the
    lab-mode path; an agent bound to a server executes through the proxy
    resolved from the server registry (I5).

    Lab-mode path: when a ``gateway`` is provided (operator-driven API runs) the
    actions are submitted through it (GatewayForge) so they are governed,
    audited, and streamed to /live and /flux (I2). Without a gateway (unit tests,
    offline harness) the historical in-memory LabForge is kept -- the recorded
    action log is identical either way, so recordings and replays are unaffected.

    When ``recorder`` is provided, the proxy-bound path is wrapped in a
    ``TracingProxy`` so each side effect a real agent produces is recorded for
    the debug console (parametrable via ``debug_enabled``). ``run_id`` tags each
    trace with the originating run so the console can filter by run (F3). The
    in-memory LabForge path produces no external side effect, so it is not traced.

    ``containment`` (Task 6) enforces the private-DNS allowlist: when True an
    agent referencing an undeclared server name raises ``ResolutionDenied`` out
    of ``resolve_proxy`` (no proxy built); the runner call-site catches it,
    audits a ``resolution_denied`` event, and fails the run safe (I2/I5). When
    False (the default) an unknown name is a dangling reference (ValueError),
    the legacy behaviour.

    Raises ResolutionDenied (containment on + undeclared name) or ValueError on
    a dangling/unsupported server reference (fail-safe: the run must fail, never
    execute against the wrong target).
    """
    server_id = agent_cfg.get("server")
    if not server_id:
        return GatewayForge(gateway) if gateway is not None else LabForge()
    # Validate the server reference up-front (fail-safe: a dangling or malformed
    # reference must raise, never silently fall back to the wrong target).
    # ``wire_proxy_url`` (the active transport route, supplied by the caller from
    # the proxy-route registry) routes the lab-mode side effects through the
    # mitmproxy overlay so it captures the bytes on the wire. None (the recette
    # default) => direct, I4 unchanged.
    proxy = resolve_proxy(
        agent_cfg,
        servers,
        default_proxy or LabHttpProxy(),
        wire_proxy_url=wire_proxy_url,
        containment=containment,
    )
    # A mock_local server on the canonical lab port is the SAME target the
    # gateway already mediates (the lab, routed by target_system). When a gateway
    # is available, govern that path through it (GatewayForge): identical
    # execution, now policy-evaluated, audited, and streamed to /live and /flux
    # (I2). A server on a different port or a real/declared target keeps the
    # direct ProxyForge -- its target is NOT the gateway's lab, so governing it
    # through the lab proxy would execute against the wrong host (fail-safe I5).
    server = next((s for s in servers if s.get("id") == server_id), None)
    if (
        gateway is not None
        and server is not None
        and server.get("mode") == "mock_local"
        and server.get("port") == _lab_port()
    ):
        return GatewayForge(gateway)
    if recorder is not None:
        proxy = TracingProxy(proxy, recorder, enabled=debug_enabled, run_id=run_id)
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
    config_store: ConfigStore | None = None,
    recorder: TraceRecorder | None = None,
    debug_enabled: bool = False,
    run_id: str | None = None,
    gateway: Gateway | None = None,
    wire_proxy_url: str | None = None,
    capture_sink: Callable[[LlmCallTrace], None] | None = None,
) -> Callable[[dict, Emit, ShouldStop], None]:
    # Opt-in in-process hook capture (G1): wrap the backend so every decision is
    # recorded to the sink, transparently to the decide->act loop. Default None =
    # no capture, zero behaviour change. The wrap is the ONLY change.
    if capture_sink is not None:
        from ..capture.capturing_llm import CapturingLlm

        llm = CapturingLlm(
            llm,
            agent_id=str(agent_cfg.get("id", "")),
            model=str(agent_cfg.get("ai_backend_id", "")),
            sink=capture_sink,
        )

    def runner(params: dict, emit: Emit, should_stop: ShouldStop) -> None:
        # Proxy resolution happens inside the runner so a dangling server
        # reference surfaces as an explicit run failure (status=failed +
        # error frame via RunManager), never as an API crash and never as
        # a silent fallback to the wrong execution target (I5 fail-safe).
        servers = config_store.list_servers() if config_store is not None else []
        # CONTAINMENT gate (Task 6): when enforced, an agent referencing an
        # undeclared server name is DENIED fail-safe. resolve_proxy raises
        # ResolutionDenied (no proxy built, no HTTP call). The event is emitted
        # HERE, the impure call-site -- resolve_proxy stays pure (I4) -- through
        # the gateway, which owns the audit sink + the event-id generator (the
        # same path every other platform event uses, I1/I2). Then the run fails
        # safe via the existing exception channel (RunManager -> status=failed),
        # so NO execution happens.
        containment = (
            bool(config_store.containment_enabled()) if config_store is not None else False
        )
        try:
            forge = forge_for_agent(
                agent_cfg,
                servers,
                recorder=recorder,
                debug_enabled=debug_enabled,
                run_id=run_id,
                gateway=gateway,
                wire_proxy_url=wire_proxy_url,
                containment=containment,
            )
        except ResolutionDenied as exc:
            _audit_resolution_denied(gateway, str(agent_cfg.get("id", "")), exc)
            # Fail safe: surface the deny through the existing run-failure channel
            # (RunManager maps a raised exception to status=failed + error frame).
            # No proxy was built and no external call was made.
            raise
        # Pacing is operational metadata (I4 / R20): resolved here in the ops
        # layer and applied by wrapping on_step, never inside lane_b's pure loop.
        pace_ms = resolve_pace(agent_cfg, servers)

        def base_on_step(i: int, step: object) -> None:
            emit("step", {"index": i, **step.to_dict()})  # type: ignore[attr-defined]
            # WS-B: also surface a granular tool-call frame so the console's
            # interactions timeline reads per-tool (name + args + correlation),
            # not only as a generic step. Additive: None for a final answer.
            tc = tool_call_frame(i, step)
            if tc is not None:
                emit("tool_call", tc)

        result = run_lane_b_agent(
            agent_id=agent_cfg["id"],
            principal=agent_cfg["principal"],
            target_system=agent_cfg["target_system"],
            goal=agent_cfg["goal"],
            capability_scope=agent_cfg["capability_scope"],
            llm=llm,
            forge=forge,
            stop_on_repeat=True,
            # F2: carry the LLM decision next to the resulting action so the
            # console can show WHY each side effect happened (decide -> act).
            on_step=_paced_on_step(base_on_step, pace_ms, should_stop),
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
        frame = {"agent_id": agent_id, "index": i, "action": action}
        # F2: include the LLM decision behind this step when available.
        to_dict = getattr(step, "to_dict", None)
        if callable(to_dict):
            decision = to_dict().get("decision")
            if decision is not None:
                frame["decision"] = decision
        emit("step", frame)
        # WS-B: granular per-tool frame alongside the generic step (additive).
        tc = tool_call_frame(i, step)
        if tc is not None:
            emit("tool_call", {"agent_id": agent_id, **tc})

    return on_step


def make_campaign_runner(
    campaign: dict,
    config_store: ConfigStore,
    recording_store: object,
    secret_store: object | None = None,
    *,
    recorder: TraceRecorder | None = None,
    debug_enabled: bool = False,
    run_id: str | None = None,
    gateway: Gateway | None = None,
    wire_proxy_url: str | None = None,
) -> Callable[[dict, Emit, ShouldStop], None]:
    """Run each campaign step as a Lane B agent, persisting one recording per
    step. A step with a stub_script runs as a mock; otherwise the agent's bound
    ai_backend drives a live LLM. Key resolution (R8): the per-backend secret
    store first, then the provider's env fallback. The key is never logged."""
    from ..llm import build_llm

    def runner(params: dict, emit: Emit, should_stop: ShouldStop) -> None:
        # CONTAINMENT gate (Task 6): same fail-safe deny as the single-agent
        # runner. A step referencing an undeclared server name is denied, audited
        # via the gateway (the audit sink owner), and fails THIS step only.
        containment = (
            bool(config_store.containment_enabled()) if config_store is not None else False
        )
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
                llm = build_llm(provider, model, base_url=backend.get("base_url"), api_key=api_key)
            servers = config_store.list_servers()  # type: ignore[attr-defined]
            try:
                # Per-agent proxy routing (I5): a dangling server reference
                # fails this step explicitly, never falls back to the default.
                forge = forge_for_agent(
                    agent_cfg,
                    servers,
                    recorder=recorder,
                    debug_enabled=debug_enabled,
                    run_id=run_id,
                    gateway=gateway,
                    wire_proxy_url=wire_proxy_url,
                    containment=containment,
                )
            except ResolutionDenied as exc:
                # Fail safe: no proxy built, no HTTP call. Audit at the impure
                # call-site (gateway owns the sink + id), then fail this step.
                _audit_resolution_denied(gateway, agent_id, exc)
                emit("step_error", {"index": idx, "agent_id": agent_id, "message": str(exc)})
                continue
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
                stop_on_repeat=True,
                # Pacing is operational metadata (I4 / R20): resolved in the ops
                # layer and applied by wrapping on_step, never inside lane_b.
                on_step=_paced_on_step(
                    _lane_b_step_emit(emit, agent_id),
                    resolve_pace(agent_cfg, servers),
                    should_stop,
                ),
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
