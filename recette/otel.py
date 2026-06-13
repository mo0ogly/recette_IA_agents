"""OpenTelemetry GenAI export of a recette run (Audit Plane, I1/I4).

Maps an orchestration run / recording to OpenTelemetry GenAI spans so an
AgentRail audit trail interoperates with any OTel backend. The attribute and
operation names are the canonical GenAI semantic conventions, taken from the real
microsoft/agent-framework ``observability.py`` (operations invoke_agent /
execute_tool, attributes gen_ai.provider.name / gen_ai.request.model /
gen_ai.agent.name / gen_ai.tool.name, span names ``invoke_agent {name}`` /
``execute_tool {tool}``).

Dependency-free and deterministic by construction (I4): span/trace ids derive
from a stable digest of the run, timestamps are logical (a fixed base + a
per-span step, never the wall clock), so the same run exports byte-identical
spans. A real OTel exporter can re-stamp wall-clock times at emit time; the
recette only needs the structure to be reproducible. The recording is read
only -- the export is a derived view, never a mutation (I1).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from .maf_orchestration import OrchestrationRun

if TYPE_CHECKING:
    from .events import AgentAction

# Canonical GenAI semantic-convention names (agent-framework observability.py).
OP = "gen_ai.operation.name"
OP_INVOKE_AGENT = "invoke_agent"
OP_EXECUTE_TOOL = "execute_tool"
PROVIDER = "gen_ai.provider.name"
SYSTEM = "gen_ai.system"
REQUEST_MODEL = "gen_ai.request.model"
AGENT_NAME = "gen_ai.agent.name"
AGENT_ID = "gen_ai.agent.id"
TOOL_NAME = "gen_ai.tool.name"
TOOL_CALL_ID = "gen_ai.tool.call.id"
# AgentRail-specific attributes for the canonical AgentActionEvent fields that
# have no GenAI equivalent (target system, identity-in-use, side-effect class).
TARGET_SYSTEM = "agentrail.target_system"
PRINCIPAL = "agentrail.principal"
ACTION_MODE = "agentrail.mode"
RESOURCE = "agentrail.resource"
APPROVED = "agentrail.approved"

_SYSTEM = "agentrail"
_STEP_NANO = 1_000_000  # logical 1ms per span; deterministic, not wall clock


@dataclass(frozen=True)
class GenAiSpan:
    """One OTel GenAI span (logical times, deterministic ids)."""

    name: str
    span_id: str
    parent_span_id: str
    trace_id: str
    start_nano: int
    end_nano: int
    attributes: dict[str, str | int] = field(default_factory=dict)


def _trace_id(seed: str) -> str:
    return hashlib.blake2b(seed.encode("utf-8"), digest_size=16).hexdigest()


def _span_id(seed: str, index: int) -> str:
    return hashlib.blake2b(f"{seed}:{index}".encode(), digest_size=8).hexdigest()


def orchestration_spans(team: dict, run: OrchestrationRun) -> list[GenAiSpan]:
    """Map an orchestration run to GenAI spans: a root invoke_agent span for the
    team, a child invoke_agent span per routed participant (hop target or order
    entry), and an execute_tool span per tool call."""
    seed = team["agent_id"]
    trace = _trace_id(seed)
    participants = {p["agent_id"]: p for p in team["participants"]}
    spans: list[GenAiSpan] = []
    idx = 0

    def _emit(name: str, parent: str, attrs: dict[str, str | int]) -> str:
        nonlocal idx
        sid = _span_id(seed, idx)
        start = idx * _STEP_NANO
        spans.append(
            GenAiSpan(
                name=name,
                span_id=sid,
                parent_span_id=parent,
                trace_id=trace,
                start_nano=start,
                end_nano=start + _STEP_NANO,
                attributes={SYSTEM: _SYSTEM, **attrs},
            )
        )
        idx += 1
        return sid

    root = _emit(
        f"{OP_INVOKE_AGENT} {team.get('name', seed)}",
        parent="",
        attrs={OP: OP_INVOKE_AGENT, AGENT_NAME: seed, AGENT_ID: seed},
    )

    # Routed participants: handoff hop targets, then order entries (seq/concur/gc/magentic).
    routed = [h.target for h in run.hops] + list(run.order)
    for agent_id in routed:
        participant = participants.get(agent_id, {})
        identity = participant.get("declared_identity", {})
        attrs: dict[str, str | int] = {
            OP: OP_INVOKE_AGENT,
            AGENT_NAME: agent_id,
            AGENT_ID: agent_id,
        }
        if identity.get("provider"):
            attrs[PROVIDER] = identity["provider"]
        if identity.get("model"):
            attrs[REQUEST_MODEL] = identity["model"]
        _emit(f"{OP_INVOKE_AGENT} {agent_id}", parent=root, attrs=attrs)

    for call in run.calls:
        attrs = {
            OP: OP_EXECUTE_TOOL,
            TOOL_NAME: call.tool_kind or "",
            TOOL_CALL_ID: str(call.seq),
            AGENT_ID: call.agent_id,
            PROVIDER: call.provider,
            REQUEST_MODEL: call.model,
        }
        _emit(f"{OP_EXECUTE_TOOL} {call.tool_kind or call.target}", parent=root, attrs=attrs)

    return spans


def action_log_spans(action_log: list[AgentAction]) -> list[GenAiSpan]:
    """Map a git/MAF agent action log (canonical AgentActionEvent rows) to GenAI
    spans: a root invoke_agent span for the agent, then one execute_tool span per
    recorded action. action_type -> gen_ai.tool.name, the action seq -> the tool
    call id, and the AgentRail-only fields (target_system, principal, mode,
    resource, approved) ride along as agentrail.* attributes. Deterministic (I4):
    ids derive from the agent id + seq, times are logical; read-only (I1)."""
    if not action_log:
        return []
    seed = action_log[0].agent_id
    trace = _trace_id(seed)
    spans: list[GenAiSpan] = []
    idx = 0

    def _emit(name: str, parent: str, attrs: dict[str, str | int]) -> str:
        nonlocal idx
        sid = _span_id(seed, idx)
        start = idx * _STEP_NANO
        spans.append(
            GenAiSpan(
                name=name,
                span_id=sid,
                parent_span_id=parent,
                trace_id=trace,
                start_nano=start,
                end_nano=start + _STEP_NANO,
                attributes={SYSTEM: _SYSTEM, **attrs},
            )
        )
        idx += 1
        return sid

    root = _emit(
        f"{OP_INVOKE_AGENT} {seed}",
        parent="",
        attrs={OP: OP_INVOKE_AGENT, AGENT_NAME: seed, AGENT_ID: seed},
    )
    for action in action_log:
        _emit(
            f"{OP_EXECUTE_TOOL} {action.action_type}",
            parent=root,
            attrs={
                OP: OP_EXECUTE_TOOL,
                TOOL_NAME: action.action_type,
                TOOL_CALL_ID: str(action.seq),
                AGENT_ID: action.agent_id,
                TARGET_SYSTEM: action.target_system,
                PRINCIPAL: action.principal,
                ACTION_MODE: action.mode,
                RESOURCE: action.resource,
                APPROVED: int(action.approved),
            },
        )
    return spans


def _attr_value(value: str | int) -> dict:
    if isinstance(value, bool):  # bool is an int subclass -- guard first
        return {"boolValue": value}
    if isinstance(value, int):
        return {"intValue": str(value)}
    return {"stringValue": value}


def to_otlp(spans: list[GenAiSpan], *, service_name: str = "agentrail-recette") -> dict:
    """Render spans as an OTLP/JSON ResourceSpans document (any OTel backend)."""
    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": service_name}}]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "recette.otel"},
                        "spans": [
                            {
                                "traceId": s.trace_id,
                                "spanId": s.span_id,
                                "parentSpanId": s.parent_span_id,
                                "name": s.name,
                                "kind": 1,  # SPAN_KIND_INTERNAL
                                "startTimeUnixNano": str(s.start_nano),
                                "endTimeUnixNano": str(s.end_nano),
                                "attributes": [
                                    {"key": k, "value": _attr_value(v)}
                                    for k, v in s.attributes.items()
                                ],
                            }
                            for s in spans
                        ],
                    }
                ],
            }
        ]
    }


def recording_to_otlp(recording_path: str | Path) -> dict:
    """Load an orchestration recording and render its OTLP GenAI spans."""
    from .orchestrate import OrchestrationRecording

    rec = OrchestrationRecording.load(recording_path)
    return to_otlp(orchestration_spans(rec.team, rec.run))
