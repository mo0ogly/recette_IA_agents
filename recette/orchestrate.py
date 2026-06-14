"""End-to-end orchestration recette: drive a team with an LLM, record, replay.

This closes the loop from a dynamic, LLM-driven multi-agent orchestration to a
deterministic recette subject:

1. ``drive`` runs a team (team.json) against any ``LlmBackend`` -- StubLlm/ReplayLlm
   (offline, deterministic) or GroqLlm (live, key GROQ_API_KEY) -- and produces an
   ``OrchestrationRun`` (hops / order / tool calls). Routing is offered to the model
   as tools (handoff_to_<target>, speak_<participant>) plus the agent's own tools.
2. ``record`` captures the run together with the ordered LLM decisions into a
   persistent ``OrchestrationRecording`` (mirrors recette.recording).
3. ``replay`` re-drives the recording with a ReplayLlm of those decisions: it
   reproduces the EXACT same run (integrity check) and renders the four-dimension
   verdict (I4). A live, non-deterministic run thus becomes replayable.
4. ``freeze_to_corpus`` writes the recording as a corpus subject (team/run/
   ground-truth derived from the judge), exactly like the hand-authored corpus.

The judge stays a pure function of (team, run); all non-determinism lives in the
backend and is captured as recorded decisions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .llm import LlmBackend, LlmDecision, Message, ReplayLlm, ToolSpec
from .maf_orchestration import (
    HandoffHop,
    OrchestrationRun,
    ToolCall,
    judge_orchestration,
    run_from_doc,
)

SCHEMA_VERSION = "1.0"
_DEFAULT_MAX_STEPS = 32
_SYSTEM = "You orchestrate a multi-agent team. Use the offered tools to act or route."

# meta describes what a generated tool name means, so the driver never parses names.
_RouteTool = tuple[str, str, str | None]  # (kind, primary, secondary) where kind in
#   "handoff" -> (handoff, target, None)
#   "speak"   -> (speak, participant, None)
#   "tool"    -> (tool, tool_kind, target)


def _participant_map(team: dict) -> dict[str, dict]:
    return {p["agent_id"]: p for p in team["participants"]}


def _agent_tools(participant: dict) -> tuple[list[ToolSpec], dict[str, _RouteTool]]:
    specs: list[ToolSpec] = []
    meta: dict[str, _RouteTool] = {}
    for i, tool in enumerate(participant.get("tools", [])):
        name = f"use_{tool['tool_kind']}_{i}"
        specs.append(
            ToolSpec(
                name=name,
                description=f"Invoke the {tool['tool_kind']} tool {tool['target']}.",
                parameters={
                    "type": "object",
                    "properties": {"approved": {"type": "boolean"}},
                },
            )
        )
        meta[name] = ("tool", tool["tool_kind"], tool["target"])
    return specs, meta


def _handoff_tools(participant: dict) -> tuple[list[ToolSpec], dict[str, _RouteTool]]:
    specs: list[ToolSpec] = []
    meta: dict[str, _RouteTool] = {}
    for h in participant.get("handoffs", []):
        name = f"handoff_to_{h['target']}"
        specs.append(
            ToolSpec(
                name=name,
                description=f"Hand off control to {h['target']}.",
                parameters={"type": "object", "properties": {}},
            )
        )
        meta[name] = ("handoff", h["target"], None)
    return specs, meta


def _speak_tools(team: dict) -> tuple[list[ToolSpec], dict[str, _RouteTool]]:
    specs: list[ToolSpec] = []
    meta: dict[str, _RouteTool] = {}
    for p in team["participants"]:
        name = f"speak_{p['agent_id']}"
        specs.append(
            ToolSpec(
                name=name,
                description=f"Give the floor to {p['agent_id']}.",
                parameters={"type": "object", "properties": {}},
            )
        )
        meta[name] = ("speak", p["agent_id"], None)
    return specs, meta


def _record_call(
    agent_id: str, participant: dict, route: _RouteTool, args: dict, seq: int
) -> ToolCall:
    _, tool_kind, target = route
    return ToolCall(
        seq=seq,
        agent_id=agent_id,
        provider=participant["declared_identity"]["provider"],
        model=participant["declared_identity"]["model"],
        target=target or "",
        tool_kind=tool_kind,
        approved=bool(args.get("approved", False)),
    )


class _Recorder:
    """Wraps a backend, capturing every decision in order for later replay."""

    def __init__(self, backend: LlmBackend) -> None:
        self._backend = backend
        self.decisions: list[LlmDecision] = []

    def decide(self, *, system: str, history: list[Message], tools: list[ToolSpec]) -> LlmDecision:
        decision = self._backend.decide(system=system, history=history, tools=tools)
        self.decisions.append(decision)
        return decision


def _drive_handoff(team: dict, backend: LlmBackend, max_steps: int) -> OrchestrationRun:
    participants = _participant_map(team)
    current = team.get("start_agent") or team["participants"][0]["agent_id"]
    hops: list[HandoffHop] = []
    calls: list[ToolCall] = []
    history: list[Message] = []
    seq = 0
    for _ in range(max_steps):
        participant = participants.get(current)
        if participant is None:
            break
        tspecs, tmeta = _agent_tools(participant)
        hspecs, hmeta = _handoff_tools(participant)
        meta = {**tmeta, **hmeta}
        decision = backend.decide(system=_SYSTEM, history=history, tools=tspecs + hspecs)
        if not decision.is_tool_call or decision.tool_name not in meta:
            break
        route = meta[decision.tool_name]
        seq += 1
        history.append(Message(role="assistant", content=decision.tool_name))
        if route[0] == "handoff":
            hops.append(HandoffHop(seq=seq, source=current, target=route[1]))
            current = route[1]
        else:
            calls.append(_record_call(current, participant, route, decision.tool_args, seq))
    return OrchestrationRun(hops=hops, calls=calls)


def _drive_linear(team: dict, backend: LlmBackend) -> OrchestrationRun:
    """Sequential/concurrent: each declared participant acts exactly once."""
    order: list[str] = []
    calls: list[ToolCall] = []
    history: list[Message] = []
    seq = 0
    for participant in team["participants"]:
        agent_id = participant["agent_id"]
        tspecs, tmeta = _agent_tools(participant)
        decision = backend.decide(system=_SYSTEM, history=history, tools=tspecs)
        order.append(agent_id)
        if decision.is_tool_call and decision.tool_name in tmeta:
            seq += 1
            calls.append(
                _record_call(
                    agent_id, participant, tmeta[decision.tool_name], decision.tool_args, seq
                )
            )
        history.append(Message(role="assistant", content=agent_id))
    return OrchestrationRun(order=order, calls=calls)


def _drive_group_chat(team: dict, backend: LlmBackend, max_steps: int) -> OrchestrationRun:
    participants = _participant_map(team)
    order: list[str] = []
    calls: list[ToolCall] = []
    history: list[Message] = []
    sspecs, smeta = _speak_tools(team)
    seq = 0
    last_speaker: str | None = None
    for _ in range(max_steps):
        tools = list(sspecs)
        tmeta: dict[str, _RouteTool] = {}
        if last_speaker is not None:
            extra, tmeta = _agent_tools(participants[last_speaker])
            tools = tools + extra
        decision = backend.decide(system=_SYSTEM, history=history, tools=tools)
        if not decision.is_tool_call:
            break
        if decision.tool_name in smeta:
            target = smeta[decision.tool_name][1]
            order.append(target)
            last_speaker = target
            history.append(Message(role="assistant", content=f"speak {target}"))
        elif decision.tool_name in tmeta and last_speaker is not None:
            seq += 1
            calls.append(
                _record_call(
                    last_speaker,
                    participants[last_speaker],
                    tmeta[decision.tool_name],
                    decision.tool_args,
                    seq,
                )
            )
        else:
            break
    return OrchestrationRun(order=order, calls=calls)


def drive(
    team: dict, backend: LlmBackend, *, max_steps: int = _DEFAULT_MAX_STEPS
) -> OrchestrationRun:
    """Drive a team against a backend and produce the run, dispatched by style."""
    style = team.get("style", "handoff")
    if style in ("sequential", "concurrent"):
        return _drive_linear(team, backend)
    if style in ("group_chat", "magentic"):
        # Both are manager-routed: the manager selects the next speaker each round.
        return _drive_group_chat(team, backend, max_steps)
    return _drive_handoff(team, backend, max_steps)


def _run_to_doc(run: OrchestrationRun, agent_id: str) -> dict:
    doc: dict = {"agent_id": agent_id}
    if run.hops:
        doc["hops"] = [{"seq": h.seq, "from": h.source, "to": h.target} for h in run.hops]
    if run.order:
        doc["order"] = list(run.order)
    if run.calls:
        doc["actions"] = [
            {
                "seq": c.seq,
                "agent_id": c.agent_id,
                "provider": c.provider,
                "model": c.model,
                "action": "invoke_tool",
                "tool_kind": c.tool_kind,
                "target": c.target,
                "approved": c.approved,
            }
            for c in run.calls
        ]
    return doc


@dataclass
class OrchestrationRecording:
    """A persistent, replayable record of one orchestration run."""

    team: dict
    run: OrchestrationRun
    decisions: list[LlmDecision] = field(default_factory=list)
    provider: str = "stub"
    model: str = ""

    def to_dict(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "provider": self.provider,
            "model": self.model,
            "team": self.team,
            "decisions": [
                {
                    "kind": d.kind,
                    "tool_name": d.tool_name,
                    "tool_args": d.tool_args,
                    "text": d.text,
                }
                for d in self.decisions
            ],
            "run": _run_to_doc(self.run, self.team["agent_id"]),
        }

    @staticmethod
    def from_dict(d: dict) -> OrchestrationRecording:
        decisions = [
            LlmDecision(
                kind=x["kind"],
                tool_name=x.get("tool_name"),
                tool_args=x.get("tool_args", {}) or {},
                text=x.get("text", ""),
            )
            for x in d.get("decisions", [])
        ]
        return OrchestrationRecording(
            team=d["team"],
            run=run_from_doc(d["run"]),
            decisions=decisions,
            provider=d.get("provider", "stub"),
            model=d.get("model", ""),
        )

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def load(path: str | Path) -> OrchestrationRecording:
        return OrchestrationRecording.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def record(
    team: dict,
    backend: LlmBackend,
    *,
    provider: str = "stub",
    model: str = "",
    max_steps: int = _DEFAULT_MAX_STEPS,
) -> OrchestrationRecording:
    """Drive the team, capturing the run and the ordered LLM decisions."""
    recorder = _Recorder(backend)
    run = drive(team, recorder, max_steps=max_steps)
    return OrchestrationRecording(
        team=team, run=run, decisions=recorder.decisions, provider=provider, model=model
    )


def replay(recording: OrchestrationRecording, *, max_steps: int = _DEFAULT_MAX_STEPS):
    """Re-drive the recording deterministically and judge it.

    Returns (reproduced_run, IdentificationResult). Raises if the reproduced run
    diverges from the recorded one (recording integrity / determinism guard)."""
    reproduced = drive(recording.team, ReplayLlm(list(recording.decisions)), max_steps=max_steps)
    if _run_to_doc(reproduced, recording.team["agent_id"]) != _run_to_doc(
        recording.run, recording.team["agent_id"]
    ):
        raise ValueError("replay diverged from the recorded run (non-deterministic driver)")
    result = judge_orchestration(recording.team, reproduced)
    return reproduced, result


def freeze_to_corpus(
    recording: OrchestrationRecording,
    dest_dir: str | Path,
    *,
    slug: str,
    category: str,
    violation_type: str | None = None,
) -> Path:
    """Write the recording as a corpus subject (team/run/ground-truth)."""
    if category == "incorrect" and violation_type is None:
        raise ValueError("an incorrect subject requires a violation_type")
    result = judge_orchestration(recording.team, recording.run)
    team = {**recording.team, "agent_id": slug}
    run_doc = _run_to_doc(recording.run, slug)
    ground_truth = {
        "agent_id": slug,
        "category": category,
        "expected_discovery": {"detectable": True, "signals": ["api_traffic", "event_stream"]},
        "expected_identification": {
            "identity": {"match": result.identity_match},
            "capabilities": {"conforms": result.capabilities_conform},
            "policy": {"compliant": result.policy_compliant},
            "behavior": {"expected": result.behavior_expected},
        },
        "expected_verdict": result.verdict,
        "rationale": f"Frozen from a {recording.provider} orchestration run ({recording.model}).",
    }
    if violation_type is not None:
        ground_truth["violation_type"] = violation_type

    out = Path(dest_dir) / slug
    out.mkdir(parents=True, exist_ok=True)
    (out / "team.json").write_text(json.dumps(team, indent=2) + "\n", encoding="utf-8")
    (out / "run.json").write_text(json.dumps(run_doc, indent=2) + "\n", encoding="utf-8")
    (out / "ground-truth.json").write_text(
        json.dumps(ground_truth, indent=2) + "\n", encoding="utf-8"
    )
    return out
