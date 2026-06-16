"""Bridge a MAF run's tool invocations -> the hook surfaces (hook_mcp / hook_sdk).

The MAF simulate path (`recette/simulate.py`) is a REAL runtime tool surface: a
subject invokes declared tools, each recorded as a `MafAction` with a
`tool_kind` (mcp, function, web_search, file_search, code_interpreter). This maps
those invocations onto the observation surfaces, so an MCP tool call becomes a
real `hook_mcp` observation -- closing the surface the G1 hook left declared-only.

Routing: ``tool_kind == "mcp"`` -> ``hook_mcp`` (the MCP transport surface);
every other in-process tool kind -> ``hook_sdk`` (the SDK call surface). Handoffs
(``action == "handoff"``, no tool_kind) reveal no tool action, so they are not a
hook observation here. Deterministic (I4): a pure function of the action log.
"""

from __future__ import annotations

from collections.abc import Iterable

from ..maf_judge import MafAction
from ..surface.recording import CaptureRecording
from ..surface.surfaces import ObservationSurface


def recording_from_maf_actions(agent_id: str, actions: Iterable[MafAction]) -> CaptureRecording:
    """Build a hook_mcp/hook_sdk CaptureRecording from a MAF action log."""
    per_surface: dict[ObservationSurface, set[str]] = {}
    for action in actions:
        if action.action != "invoke_tool" or not action.tool_kind:
            continue
        surface = (
            ObservationSurface.HOOK_MCP
            if action.tool_kind == "mcp"
            else ObservationSurface.HOOK_SDK
        )
        key = f"{action.tool_kind}:{action.target}"
        per_surface.setdefault(surface, set()).add(key)
    surfaces = {surface: tuple(sorted(keys)) for surface, keys in per_surface.items()}
    return CaptureRecording(agent_id=agent_id, surfaces=surfaces)
