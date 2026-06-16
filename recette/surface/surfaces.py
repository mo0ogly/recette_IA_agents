"""Project one run's two views onto RailNode's observation surfaces (pure, I4).

A run yields two deterministic views (founding doc 2026-06-16, sec. 5):
- the HOOK view = the mediated/structured calls (``ProxyTrace`` dicts): what an
  in-process shim (subprocess / MCP / SDK) sees.
- the WIRE view = the network flows (``WireFlow`` dicts): what an eBPF / syscall
  probe sees on the wire.

A ghost agent that bypasses the SDK produces a WIRE flow with no HOOK trace, so
it is invisible to the hook surfaces and visible to the wire surface. Projection
is a pure function of (proxy_traces, wire_flows): no clock, no random, sorted
output, replay-stable.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ObservationSurface(StrEnum):
    """The surfaces RailNode can observe an agent on (AgentRail RFC + diagram)."""

    HOOK_SUBPROCESS = "hook_subprocess"
    HOOK_MCP = "hook_mcp"
    HOOK_SDK = "hook_sdk"
    EBPF_WIRE = "ebpf_wire"


# The inline hook family: all three see the same mediated/structured call.
HOOK_SURFACES: tuple[ObservationSurface, ...] = (
    ObservationSurface.HOOK_SUBPROCESS,
    ObservationSurface.HOOK_MCP,
    ObservationSurface.HOOK_SDK,
)


@dataclass(frozen=True)
class SurfaceObservation:
    """What is visible on one surface: a sorted tuple of stable identifiers."""

    surface: ObservationSurface
    visible: tuple[str, ...]


def _hook_key(trace: dict) -> str:
    """Stable identifier of a mediated call (the structured intent)."""
    return f"{trace.get('action_type', '')}:{trace.get('resource', '')}"


def _wire_key(flow: dict) -> str:
    """Stable identifier of a network flow (method host:port/path)."""
    return (
        f"{flow.get('method', '')} {flow.get('host', '')}:"
        f"{flow.get('port', '')}{flow.get('path', '')}"
    )


def project_surfaces(
    *, proxy_traces: list[dict], wire_flows: list[dict]
) -> dict[ObservationSurface, SurfaceObservation]:
    """Map the two run views onto every observation surface (pure, sorted)."""
    hook_visible = tuple(sorted(_hook_key(t) for t in proxy_traces))
    wire_visible = tuple(sorted(_wire_key(f) for f in wire_flows))
    result: dict[ObservationSurface, SurfaceObservation] = {}
    for surface in HOOK_SURFACES:
        result[surface] = SurfaceObservation(surface=surface, visible=hook_visible)
    result[ObservationSurface.EBPF_WIRE] = SurfaceObservation(
        surface=ObservationSurface.EBPF_WIRE, visible=wire_visible
    )
    return result
