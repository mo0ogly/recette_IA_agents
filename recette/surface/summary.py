"""Score the committed surface corpus into one detection scorecard.

The surface recette asks the founding question -- "does the tool SEE the agent on
each observation surface?" -- over the corpus/surface subjects. This helper is
the single source of that scoring (used by both the ``recette surface`` CLI and
the discovery-overview API), so the CLI scorecard and the dashboard tile always
agree.

Pure + deterministic (I4): the reference adapter is a pure function of each
subject's projected surfaces. Fail-safe: if the corpus cannot be loaded, an empty
scorecard is returned (zero agents, ok) rather than raising into a caller.
"""

from __future__ import annotations

import logging

from .corpus import load_surface_subjects
from .detect import ReferenceSurfaceDiscoveryAdapter, detect_agent
from .scorecard import DetectionScorecard, score_detections

logger = logging.getLogger(__name__)


def surface_corpus_scorecard() -> DetectionScorecard:
    """Detect every surface-corpus subject with the reference adapter and score.

    Mirrors the per-surface recette: project each subject's hook (proxy traces)
    and wire (flows) views, run the adapter on each surface, then score the
    detections (a subject seen on no surface is a false negative -- a ghost).
    """
    try:
        subjects = load_surface_subjects()
    except OSError as exc:
        logger.warning("surface corpus unreadable: %s -> empty scorecard", exc)
        return score_detections([])

    adapter = ReferenceSurfaceDiscoveryAdapter()
    detections = [
        detect_agent(
            agent_id=subject["agent_id"],
            proxy_traces=subject["run"]["proxy_traces"],
            wire_flows=subject["run"]["wire_flows"],
            adapter=adapter,
        )
        for subject in subjects
    ]
    return score_detections(detections)
