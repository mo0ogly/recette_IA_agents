"""Per-surface discovery seam + reference oracle.

``SurfaceDiscoveryAdapter`` is the protocol a real discovery tool (the discovery probe)
implements -- given what is visible on one surface, does it detect an agent?
``ReferenceSurfaceDiscoveryAdapter`` is the correct offline oracle (detected iff
anything is visible). ``detect_agent`` runs every surface and aggregates: an
agent detected on NO surface is the thesis failure (founding doc, sec. 0).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from recette.adapters import DiscoveryResult

from .surfaces import ObservationSurface, SurfaceObservation, project_surfaces


@runtime_checkable
class SurfaceDiscoveryAdapter(Protocol):
    def detect_on(self, observation: SurfaceObservation) -> DiscoveryResult: ...


class ReferenceSurfaceDiscoveryAdapter:
    """Correct oracle: an agent is detected on a surface iff something is visible."""

    def detect_on(self, observation: SurfaceObservation) -> DiscoveryResult:
        return DiscoveryResult(
            detected=bool(observation.visible), signals=list(observation.visible)
        )


@dataclass(frozen=True)
class SurfaceDetection:
    surface: ObservationSurface
    detected: bool


@dataclass(frozen=True)
class AgentDetection:
    agent_id: str
    per_surface: tuple[SurfaceDetection, ...]
    detected_anywhere: bool


def detect_agent(
    *,
    agent_id: str,
    proxy_traces: list[dict],
    wire_flows: list[dict],
    adapter: SurfaceDiscoveryAdapter,
) -> AgentDetection:
    """Project the run, run the adapter on each surface, aggregate (pure, I4)."""
    surfaces = project_surfaces(proxy_traces=proxy_traces, wire_flows=wire_flows)
    per_surface = tuple(
        SurfaceDetection(surface=surface, detected=adapter.detect_on(obs).detected)
        for surface, obs in sorted(surfaces.items(), key=lambda kv: kv[0].value)
    )
    return AgentDetection(
        agent_id=agent_id,
        per_surface=per_surface,
        detected_anywhere=any(d.detected for d in per_surface),
    )
