"""LB3 -- the Lane B agent loop.

An LLM decides the next action within a bounded capability set; each tool call runs through
the mediated forge (I5) and is recorded. The output is an ordered AgentAction log (the same
shape as a Lane A scenario) plus a replayable Recording.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .events import AgentAction
from .forge import GitForge, LabForge
from .llm import LlmBackend, Message
from .recording import RecordedStep, Recording
from .tools import build_tools, execute_tool


@dataclass
class LaneBResult:
    actions: list[AgentAction]
    recording: Recording


def _system_prompt(goal: str, target_system: str, capability_scope: list[str]) -> str:
    tools = ", ".join(sorted(set(capability_scope)))
    return (
        "You are an autonomous agent operating on a "
        f"{target_system} system. Your goal: {goal}\n"
        f"You may only use these tools: {tools}. Call one tool at a time with a 'resource' "
        "argument. When the goal is met, stop with a final answer."
    )


def _result_text(action: AgentAction) -> str:
    return f"ok: {action.action_type} on {action.resource} (mode={action.mode})"


def run_agent(
    *,
    agent_id: str,
    principal: str,
    target_system: str,
    goal: str,
    capability_scope: list[str],
    llm: LlmBackend,
    forge: GitForge | None = None,
    provider: str = "stub",
    model: str = "",
    max_steps: int = 10,
    on_step: Callable[[int, RecordedStep], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> LaneBResult:
    """Run the decide->act loop until a final answer or max_steps. Deterministic given a
    deterministic backend (StubLlm/ReplayLlm) + LabForge."""
    forge = forge or LabForge()
    tools = build_tools(capability_scope)
    system = _system_prompt(goal, target_system, capability_scope)
    history: list[Message] = [Message("user", goal)]
    recording = Recording(
        agent_id=agent_id,
        principal=principal,
        target_system=target_system,
        goal=goal,
        provider=provider,
        model=model,
    )
    actions: list[AgentAction] = []

    for i in range(max_steps):
        if should_stop is not None and should_stop():
            break
        decision = llm.decide(system=system, history=history, tools=tools)
        if not decision.is_tool_call:
            step = RecordedStep(decision=decision, action=None)
            recording.steps.append(step)
            if on_step is not None:
                on_step(i, step)
            break
        action = execute_tool(
            forge,
            agent_id=agent_id,
            principal=principal,
            target_system=target_system,
            decision=decision,
        )
        actions.append(action)
        step = RecordedStep(decision=decision, action=action.to_dict())
        recording.steps.append(step)
        if on_step is not None:
            on_step(i, step)
        history.append(Message("assistant", f"calling {decision.tool_name}"))
        history.append(Message("tool", _result_text(action), tool_name=decision.tool_name))

    return LaneBResult(actions=actions, recording=recording)
