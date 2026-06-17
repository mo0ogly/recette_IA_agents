"""Granular per-step run frames for the debug console.

A Lane B step fuses the LLM decision and the resulting action into one
generic ``step`` frame. For a readable *interactions* timeline the console
also wants each tool invocation surfaced as its own unit: the tool name, the
arguments the agent chose, and a correlation to the executed action -- whose
request/response pair lives in the proxy-trace network log. This module
derives that unit from a recorded step as a pure function (I4: no clock, no
randomness, no I/O), so it is deterministic and unit-testable in isolation.

The ``tool_call`` frame is emitted IN ADDITION to the existing ``step`` frame
(never instead of it): consumers that only know ``step`` keep working, and the
debug view gains a per-tool breakdown. A final answer carries no tool call, so
it yields no ``tool_call`` frame.
"""

from __future__ import annotations

from typing import Any


def _step_dict(step: Any) -> dict:
    """Normalize a recorded step (object with ``to_dict`` or a plain dict)."""
    to_dict = getattr(step, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    return step if isinstance(step, dict) else {}


def tool_call_frame(index: int, step: Any) -> dict | None:
    """Return a granular tool-call frame for ``step``, or ``None`` when the
    step is not a tool invocation.

    The frame correlates to the side-effect network log via ``event_id`` (the
    executed action's id), so the console can fold the requested arguments and
    the request/response exchange into a single expandable interaction.
    """
    data = _step_dict(step)
    decision = data.get("decision") or {}
    if decision.get("kind") != "tool_call":
        return None
    action = data.get("action")
    event_id = action.get("event_id") if isinstance(action, dict) else None
    return {
        "index": index,
        "name": decision.get("tool_name"),
        "args": decision.get("tool_args") or {},
        "event_id": event_id,
        "action": action,
    }
