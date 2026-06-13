"""Multi-turn simulation loop for a standard-aligned (MAF) subject.

Transposes the langwatch/scenario idea (a UserSimulatorAgent drives the subject
over several turns, then a judge renders a verdict) onto the recette's own LLM
abstraction (recette.llm.LlmBackend) -- no external dependency, no litellm.

The loop drives the subject through user turns, captures every tool call as a
MafAction (against the declared agent-spec), enforces approval gates (I6: an
approval=always tool only counts as approved if the injected approver grants it,
never optimistically), and returns an action log the existing judge_maf scores
on the four dimensions.

Determinism: the loop is a pure function of its inputs. Inject StubLlm/ReplayLlm
(recette.llm) for a byte-stable replay (I4); a real provider backend is used only
in real_mode, where the run is recorded, not replayed.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from .llm import LlmBackend, Message, ToolSpec
from .maf_judge import MafAction

# An approver decides whether an approval-gated tool call may proceed (I6).
# Default: deny -- nothing is approved unless an approver explicitly grants it,
# so a gated tool invoked under the default is recorded as unapproved (a policy
# violation the judge will flag), never auto-approved.
Approver = Callable[[MafAction], bool]


def _deny_all(_: MafAction) -> bool:
    return False


# A user-turn provider yields the next user message given the conversation so far,
# or None to end the conversation. A plain list of strings is the scripted form.
UserTurns = Sequence[str] | Callable[[list[Message]], "str | None"]


@dataclass(frozen=True)
class LlmUserSimulator:
    """A UserSimulatorAgent driven by an LlmBackend (transposes scenario's idea).

    Generates the next user message from the persona and the conversation so far.
    Returns None (ends the conversation) on an empty reply or the stop word, so a
    StubLlm/ReplayLlm makes the whole simulation deterministic (I4)."""

    backend: LlmBackend
    persona: str
    stop_word: str = "STOP"

    def __call__(self, history: list[Message]) -> str | None:
        decision = self.backend.decide(system=self.persona, history=history, tools=[])
        text = decision.text.strip()
        if not text or text.upper().startswith(self.stop_word):
            return None
        return text


@dataclass(frozen=True)
class SimResult:
    action_log: list[MafAction]
    transcript: list[Message]
    stopped_reason: str  # "completed" | "max_turns"


@dataclass(frozen=True)
class _ToolBinding:
    tool_kind: str | None  # None for handoff
    target: str
    approval: str  # "never" | "always" | "n/a" (handoff)


def tools_from_spec(spec: dict) -> tuple[list[ToolSpec], dict[str, _ToolBinding]]:
    """Derive the callable tool surface and a name->binding registry from an agent-spec.

    The tool name exposed to the subject is its target (unique within a deduped
    scope); a handoff is exposed as ``handoff:<target>``.
    """
    tools: list[ToolSpec] = []
    registry: dict[str, _ToolBinding] = {}
    for cap in spec["capability_scope"]:
        if cap["action"] == "invoke_tool":
            name = cap["target"]
            registry[name] = _ToolBinding(cap["tool_kind"], cap["target"], cap["approval"])
            tools.append(
                ToolSpec(
                    name=name,
                    description=f"{cap['tool_kind']} tool (approval={cap['approval']})",
                    parameters={"type": "object", "properties": {}},
                )
            )
        else:  # handoff
            name = f"handoff:{cap['target']}"
            registry[name] = _ToolBinding(None, cap["target"], "n/a")
            tools.append(
                ToolSpec(
                    name=name,
                    description=f"hand off to agent {cap['target']}",
                    parameters={"type": "object", "properties": {}},
                )
            )
    return tools, registry


def _record(
    seq: int, agent_id: str, provider: str, model: str, name: str, binding: _ToolBinding | None
) -> MafAction:
    if binding is None:
        # The subject called a tool that is not in its declared scope: record it
        # faithfully (unknown kind) so the capability check flags the overreach.
        return MafAction(
            seq=seq,
            agent_id=agent_id,
            provider=provider,
            model=model,
            action="invoke_tool",
            target=name,
            tool_kind=None,
            approved=False,
        )
    action = "handoff" if binding.tool_kind is None else "invoke_tool"
    return MafAction(
        seq=seq,
        agent_id=agent_id,
        provider=provider,
        model=model,
        action=action,
        target=binding.target,
        tool_kind=binding.tool_kind,
        approved=False,
    )


def _next_user_turn(user_turns: UserTurns, history: list[Message], index: int, cap: int):
    """Return the next user message (or None to stop), for scripted or LLM-driven users."""
    if callable(user_turns):
        if index >= cap:
            return None
        return user_turns(history)
    return user_turns[index] if index < len(user_turns) else None


def simulate(
    *,
    spec: dict,
    subject: LlmBackend,
    user_turns: UserTurns,
    max_tool_steps: int = 6,
    max_user_turns: int = 8,
    approver: Approver = _deny_all,
) -> SimResult:
    """Drive ``subject`` through ``user_turns`` and return its action log.

    ``user_turns`` is either a scripted list of strings or a callable
    (e.g. LlmUserSimulator) yielding the next message until it returns None.
    For each user message the subject may emit a chain of tool calls before a
    final answer (bounded by ``max_tool_steps``). Approval-gated tool calls are
    submitted to ``approver``; a denial records the call as unapproved (I6).
    """
    identity = spec["declared_identity"]
    provider, model = identity["provider"], identity["model"]
    agent_id = spec["agent_id"]
    system = spec.get("description", spec["name"])
    tools, registry = tools_from_spec(spec)

    history: list[Message] = []
    log: list[MafAction] = []
    seq = 0
    stopped_reason = "completed"

    turn_index = 0
    while True:
        user_msg = _next_user_turn(user_turns, history, turn_index, max_user_turns)
        if user_msg is None:
            break
        turn_index += 1
        history.append(Message(role="user", content=user_msg))
        steps = 0
        while True:
            if steps >= max_tool_steps:
                stopped_reason = "max_turns"
                break
            steps += 1
            decision = subject.decide(system=system, history=history, tools=tools)
            if not decision.is_tool_call:
                history.append(Message(role="assistant", content=decision.text))
                break
            name = decision.tool_name or ""
            binding = registry.get(name)
            action = _record(seq, agent_id, provider, model, name, binding)
            if binding is not None and binding.approval == "always":
                action = MafAction(
                    seq=action.seq,
                    agent_id=action.agent_id,
                    provider=action.provider,
                    model=action.model,
                    action=action.action,
                    target=action.target,
                    tool_kind=action.tool_kind,
                    approved=approver(action),
                )
            log.append(action)
            seq += 1
            history.append(Message(role="assistant", content="", tool_name=name))
            history.append(Message(role="tool", content=f"ok:{name}", tool_name=name))

    return SimResult(action_log=log, transcript=history, stopped_reason=stopped_reason)
