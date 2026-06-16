"""Ingest a discoveryprobe broker capture recording into the surface scorecard.

The native broker (``discoveryprobe-broker``, design sec. 12.3) emits, per agent,
a capture recording already projected onto the observation surfaces::

    {"agent_id": "...", "surfaces": {"ebpf_wire": ["exec:pr-bot:42"], ...}}

The surface names match :class:`ObservationSurface` exactly -- that string is the
Rust/Python bridge contract (``discoveryprobe-core::ObservationSurface`` ==
``recette/surface/surfaces.py``). This module turns that recording back into the
SAME :class:`AgentDetection` / :class:`DetectionScorecard` the in-bench
projection produces, so the SOURCE of the observations is interchangeable: a live
eBPF capture and the deterministic in-bench projection feed one source-agnostic,
replay-stable judge (I4). An unknown surface name is a bridge mismatch and raises
loudly rather than being silently dropped.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from .detect import (
    AgentDetection,
    ReferenceSurfaceDiscoveryAdapter,
    SurfaceDetection,
    SurfaceDiscoveryAdapter,
)
from .scorecard import DetectionScorecard, score_detections
from .surfaces import ObservationSurface, SurfaceObservation


@dataclass(frozen=True)
class CaptureRecording:
    """One agent's capture: the visible identifiers per observation surface."""

    agent_id: str
    surfaces: dict[ObservationSurface, tuple[str, ...]]

    @staticmethod
    def from_dict(data: dict) -> CaptureRecording:
        """Parse a recording dict; an unknown surface name raises ValueError
        (a bridge mismatch must never be silently swallowed)."""
        if "agent_id" not in data:
            raise ValueError("recording is missing 'agent_id'")
        raw = data.get("surfaces") or {}
        surfaces: dict[ObservationSurface, tuple[str, ...]] = {}
        for name, keys in raw.items():
            surface = ObservationSurface(name)  # ValueError on unknown surface
            surfaces[surface] = tuple(keys)
        return CaptureRecording(agent_id=data["agent_id"], surfaces=surfaces)


def detect_from_recording(
    recording: CaptureRecording, adapter: SurfaceDiscoveryAdapter
) -> AgentDetection:
    """Run the discovery adapter on every surface of a capture recording.

    A surface absent from the recording is treated as nothing-visible, so an
    agent captured nowhere is detected nowhere -- the ghost / false-negative case
    the thesis must surface (founding doc sec. 0). Pure and deterministic: the
    surfaces are walked in a stable order.
    """
    per_surface = tuple(
        SurfaceDetection(
            surface=surface,
            detected=adapter.detect_on(
                SurfaceObservation(surface=surface, visible=recording.surfaces.get(surface, ()))
            ).detected,
        )
        for surface in sorted(ObservationSurface, key=lambda s: s.value)
    )
    return AgentDetection(
        agent_id=recording.agent_id,
        per_surface=per_surface,
        detected_anywhere=any(d.detected for d in per_surface),
    )


def _extract_recordings(payload: object) -> list[dict]:
    """Pull the recordings list out of a broker payload.

    Accepts a bare list of recordings, or the broker response envelope
    ``{"status": "ok", "recordings": [...]}``. A rejected capture
    (``{"status": "rejected", "reason": ...}``) raises, since there is nothing
    to score.
    """
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        if payload.get("status") == "rejected":
            raise ValueError(f"broker rejected the capture: {payload.get('reason')}")
        recordings = payload.get("recordings")
        if isinstance(recordings, list):
            return recordings
    raise ValueError("unrecognised broker payload: expected a recordings list or envelope")


def score_recording(
    recordings_json: str, adapter: SurfaceDiscoveryAdapter | None = None
) -> DetectionScorecard:
    """Score a broker capture recording (JSON) into a detection scorecard.

    ``adapter`` defaults to the reference oracle; a real RailNode build plugs in
    via the same :class:`SurfaceDiscoveryAdapter` protocol, so this is also the
    conformance seam (reference probe vs team tool on the same recording).
    """
    used_adapter = adapter or ReferenceSurfaceDiscoveryAdapter()
    payload = json.loads(recordings_json)
    detections = [
        detect_from_recording(CaptureRecording.from_dict(raw), used_adapter)
        for raw in _extract_recordings(payload)
    ]
    return score_detections(detections)
