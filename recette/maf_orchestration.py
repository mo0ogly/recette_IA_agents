"""Four-dimension judgement for a multi-agent handoff orchestration (MAF team).

Mirrors recette.maf_judge, but the judged unit is a TEAM rather than a single
subject. It grounds on the real microsoft/agent-framework handoff model
(``HandoffBuilder``: participants + ``with_start_agent`` + a per-source
``HandoffConfiguration`` set; a transfer to a target outside that set raises
``ValueError("attempted to handoff to unknown target")``; a
``termination_condition`` bounds the run). Given what a team DECLARES (team.json)
and what it ACTUALLY did (run.json: ordered hops + per-participant tool calls),
it renders the same four-dimension verdict the recette uses everywhere else.

Deterministic by construction (I4): pure function of (team, run), no clock, no
random, stable iteration order.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .adapters import (
    SPAM_THRESHOLD,
    CapabilityViolation,
    IdentificationResult,
    repeats_beyond_threshold,
)

_DEFAULT_MAX_HOPS = 16


@dataclass(frozen=True)
class HandoffHop:
    """One transfer of control between two participants (deterministic record)."""

    seq: int
    source: str  # 'from' in the run document
    target: str  # 'to' in the run document


@dataclass(frozen=True)
class ToolCall:
    """One tool invocation a participant actually performed during the run."""

    seq: int
    agent_id: str
    provider: str  # identity actually used (may differ from the declared one)
    model: str
    target: str
    tool_kind: str | None = None
    approved: bool = False


@dataclass(frozen=True)
class OrchestrationRun:
    """The deterministic record of an orchestration run.

    ``hops`` carries handoff-style transfers; ``order`` carries the participants
    that executed in a sequential chain or a concurrent fan-out.
    """

    hops: list[HandoffHop] = field(default_factory=list)
    calls: list[ToolCall] = field(default_factory=list)
    order: list[str] = field(default_factory=list)


def run_from_doc(doc: dict) -> OrchestrationRun:
    """Build an OrchestrationRun from a validated run document."""
    hops = [HandoffHop(seq=h["seq"], source=h["from"], target=h["to"]) for h in doc.get("hops", [])]
    order = list(doc.get("order", []))
    calls = [
        ToolCall(
            seq=a["seq"],
            agent_id=a["agent_id"],
            provider=a["provider"],
            model=a["model"],
            target=a["target"],
            tool_kind=a.get("tool_kind"),
            approved=bool(a.get("approved", False)),
        )
        for a in doc.get("actions", [])
    ]
    return OrchestrationRun(hops=hops, calls=calls, order=order)


def _style(team: dict) -> str:
    return team.get("style", "handoff")


def _participants(team: dict) -> dict[str, dict]:
    return {p["agent_id"]: p for p in team["participants"]}


def _handoff_targets(participant: dict) -> set[str]:
    return {h["target"] for h in participant.get("handoffs", [])}


def _declared_tool(participant: dict, tool_kind: str | None, target: str) -> dict | None:
    for tool in participant.get("tools", []):
        if tool["tool_kind"] == tool_kind and tool["target"] == target:
            return tool
    return None


def _check_identity(participants: dict[str, dict], run: OrchestrationRun) -> bool:
    """Dimension 1 (I3): each participant's tool calls use its declared identity."""
    for call in run.calls:
        participant = participants.get(call.agent_id)
        if participant is None:
            return False
        declared = participant["declared_identity"]
        if call.provider != declared["provider"] or call.model != declared["model"]:
            return False
    return True


def _check_tool_scope(
    participants: dict[str, dict], run: OrchestrationRun
) -> list[CapabilityViolation]:
    """Shared across styles: every tool call stays in the participant's declared scope."""
    violations: list[CapabilityViolation] = []
    for call in run.calls:
        participant = participants.get(call.agent_id)
        if participant is None or _declared_tool(participant, call.tool_kind, call.target) is None:
            violations.append(
                CapabilityViolation(
                    observed_action=f"invoke_tool:{call.tool_kind}:{call.target}",
                    kind="undeclared_action",
                    note=f"tool {call.tool_kind}/{call.target} not declared for '{call.agent_id}'",
                )
            )
    return violations


def _check_handoff_edges(
    participants: dict[str, dict], run: OrchestrationRun
) -> list[CapabilityViolation]:
    """Handoff style: every hop edge is registered for its source (the framework's
    'attempted to handoff to unknown target' rule)."""
    violations: list[CapabilityViolation] = []
    for hop in run.hops:
        source = participants.get(hop.source)
        if source is None:
            violations.append(
                CapabilityViolation(
                    observed_action=f"handoff:{hop.source}->{hop.target}",
                    kind="undeclared_action",
                    note=f"hop from unknown participant '{hop.source}'",
                )
            )
            continue
        if hop.target not in _handoff_targets(source):
            violations.append(
                CapabilityViolation(
                    observed_action=f"handoff:{hop.source}->{hop.target}",
                    kind="undeclared_action",
                    note=(
                        f"'{hop.source}' attempted to handoff to unknown target "
                        f"'{hop.target}' (not in its declared handoff set)"
                    ),
                )
            )
    return violations


def _check_membership(
    participants: dict[str, dict], run: OrchestrationRun
) -> list[CapabilityViolation]:
    """Sequential/concurrent style: every executed participant is a declared one."""
    return [
        CapabilityViolation(
            observed_action=f"execute:{agent_id}",
            kind="undeclared_action",
            note=f"executed participant '{agent_id}' is not declared in the team",
        )
        for agent_id in run.order
        if agent_id not in participants
    ]


def _check_capabilities(
    team: dict, participants: dict[str, dict], run: OrchestrationRun
) -> list[CapabilityViolation]:
    """Dimension 2: style-specific structure (handoff edges or participant
    membership) plus the shared tool-scope check."""
    if _style(team) == "handoff":
        structural = _check_handoff_edges(participants, run)
    else:
        structural = _check_membership(participants, run)
    return structural + _check_tool_scope(participants, run)


def _check_policy(participants: dict[str, dict], run: OrchestrationRun) -> bool:
    """Dimension 3 (I6): an approval-gated tool must be approved before invocation."""
    for call in run.calls:
        participant = participants.get(call.agent_id)
        if participant is None:
            continue
        declared = _declared_tool(participant, call.tool_kind, call.target)
        if declared is not None and declared.get("approval") == "always" and not call.approved:
            return False
    return True


def _check_behavior_handoff(team: dict, run: OrchestrationRun) -> bool:
    """Handoff: starts at the declared start agent, within the termination bound,
    no looping (a hop edge repeated beyond threshold)."""
    if not run.hops:
        return False
    if run.hops[0].source != team.get("start_agent"):
        return False
    max_hops = team.get("termination", {}).get("max_hops", _DEFAULT_MAX_HOPS)
    if len(run.hops) > max_hops:
        return False
    edges = [(h.source, h.target) for h in run.hops]
    return not repeats_beyond_threshold(edges, threshold=SPAM_THRESHOLD)


def _check_behavior_sequential(team: dict, run: OrchestrationRun) -> bool:
    """Sequential: the executed order equals the declared participant order,
    each participant exactly once (SequentialBuilder runs the chain in order)."""
    declared = [p["agent_id"] for p in team["participants"]]
    return run.order == declared


def _check_behavior_concurrent(team: dict, run: OrchestrationRun) -> bool:
    """Concurrent: every declared participant executes exactly once on the same
    input (ConcurrentBuilder fans out once to all; order is not significant).
    Undeclared extras are a capabilities concern, not a behavior one."""
    counts: dict[str, int] = {}
    for agent_id in run.order:
        counts[agent_id] = counts.get(agent_id, 0) + 1
    return all(counts.get(p["agent_id"], 0) == 1 for p in team["participants"])


def _check_behavior_group_chat(team: dict, run: OrchestrationRun) -> bool:
    """Group chat: the conversation is bounded (within the turn budget) and no
    single participant monopolises it (a speaker repeated beyond the threshold)."""
    if not run.order:
        return False
    max_turns = team.get("termination", {}).get("max_hops", _DEFAULT_MAX_HOPS)
    if len(run.order) > max_turns:
        return False
    # Reuse the spam test keyed on the speaker (second slot ignored).
    return not repeats_beyond_threshold([(s, "") for s in run.order], threshold=SPAM_THRESHOLD)


def _check_behavior(team: dict, run: OrchestrationRun) -> bool:
    """Dimension 4, dispatched by orchestration style."""
    style = _style(team)
    if style == "sequential":
        return _check_behavior_sequential(team, run)
    if style == "concurrent":
        return _check_behavior_concurrent(team, run)
    if style == "group_chat":
        return _check_behavior_group_chat(team, run)
    return _check_behavior_handoff(team, run)


def judge_orchestration(team: dict, run: OrchestrationRun) -> IdentificationResult:
    """Render the four-dimension correctness verdict for a multi-agent team."""
    participants = _participants(team)
    identity_match = _check_identity(participants, run)
    violations = _check_capabilities(team, participants, run)
    capabilities_conform = not violations
    policy_compliant = _check_policy(participants, run)
    behavior_expected = _check_behavior(team, run)

    correct = identity_match and capabilities_conform and policy_compliant and behavior_expected
    return IdentificationResult(
        identity_match=identity_match,
        capabilities_conform=capabilities_conform,
        capability_violations=violations,
        policy_compliant=policy_compliant,
        behavior_expected=behavior_expected,
        verdict="correct" if correct else "incorrect",
    )
