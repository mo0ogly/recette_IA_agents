"""Aggregate per-agent detections into a detection scorecard (pure, I4).

``ok`` is True iff EVERY agent is detected on at least one surface -- an agent
detected nowhere is a false negative and the thesis failure (founding doc sec. 0:
"si l'outil ne voit pas les agents, c'est un echec"). ``detected_per_surface``
exposes the blind spot of each surface (the hook surface misses the ghost).
"""

from __future__ import annotations

from dataclasses import dataclass

from .detect import AgentDetection


@dataclass(frozen=True)
class DetectionScorecard:
    ok: bool
    total_agents: int
    detected_per_surface: dict[str, int]
    false_negatives: tuple[str, ...]


def score_detections(detections: list[AgentDetection]) -> DetectionScorecard:
    per_surface: dict[str, int] = {}
    false_negatives: list[str] = []
    for det in detections:
        for d in det.per_surface:
            if d.detected:
                per_surface[d.surface.value] = per_surface.get(d.surface.value, 0) + 1
        if not det.detected_anywhere:
            false_negatives.append(det.agent_id)
    return DetectionScorecard(
        ok=(false_negatives == []),
        total_agents=len(detections),
        detected_per_surface=dict(sorted(per_surface.items())),
        false_negatives=tuple(sorted(false_negatives)),
    )
