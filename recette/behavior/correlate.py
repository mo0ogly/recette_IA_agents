"""Correlate the static discovery scan with the runtime behavioral wave.

Discovery PREDICTS risk from source; the behavioral engine MEASURES it at
runtime. correlate() joins them through the agent identity map and classifies
each agent into a 2x2 quadrant. The headline research signal is ``static_blind``
-- a source the scanner called clean that behaves dirty at runtime.

Pure (I4): a function of (discovery_facts, behavior_reports, links, thresholds);
no clock, no random, sorted/stable output -> byte-identical on replay.
"""

from __future__ import annotations

from .links import Link
from .report import TOOL_VERSION

_QUADRANT = {
    (False, False): "agree_clean",
    (False, True): "static_blind",
    (True, False): "static_overflag",
    (True, True): "agree_dirty",
}


def correlate(
    discovery_facts: dict[str, dict],
    behavior_reports: dict[str, dict],
    links: list[Link],
    thresholds: dict,
) -> dict:
    """Classify each linked agent into a quadrant. Fail-loud on missing sides."""
    dirty_threshold = int(thresholds.get("runtime_dirty", 50))
    rows: list[dict] = []
    unresolved: list[dict] = []
    quadrants: dict[str, list[str] | int] = {
        "agree_clean": 0,
        "agree_dirty": 0,
        "static_blind": [],
        "static_overflag": [],
    }

    for ln in sorted(links, key=lambda x: x.agent_id):
        disc = discovery_facts.get(ln.discovery_subject or "")
        beh = behavior_reports.get(ln.agent_id)
        if disc is None:
            unresolved.append({"agent_id": ln.agent_id, "reason": "discovery_missing"})
            continue
        if beh is None:
            unresolved.append({"agent_id": ln.agent_id, "reason": "evidence_missing"})
            continue

        static_flagged = bool(disc.get("flagged"))
        runtime_dirty = int(beh.get("behavioral_score", 0)) >= dirty_threshold
        quadrant = _QUADRANT[(static_flagged, runtime_dirty)]
        rows.append(
            {
                "agent_id": ln.agent_id,
                "discovery_subject": ln.discovery_subject,
                "static_flagged": static_flagged,
                "runtime_dirty": runtime_dirty,
                "behavioral_score": int(beh.get("behavioral_score", 0)),
                "quadrant": quadrant,
                "agreement": static_flagged == runtime_dirty,
            }
        )
        if quadrant in ("agree_clean", "agree_dirty"):
            quadrants[quadrant] += 1  # type: ignore[operator]
        else:
            quadrants[quadrant].append(ln.agent_id)  # type: ignore[union-attr]

    # coverage: discovery subjects present in facts but linked to no agent
    linked_subjects = {ln.discovery_subject for ln in links if ln.discovery_subject}
    coverage_gaps = [
        {"discovery_subject": s} for s in sorted(discovery_facts) if s not in linked_subjects
    ]

    return {
        "rows": sorted(rows, key=lambda r: r["agent_id"]),
        "quadrants": quadrants,
        "unresolved": sorted(unresolved, key=lambda u: u["agent_id"]),
        "coverage_gaps": coverage_gaps,
        "thresholds": {"runtime_dirty": dirty_threshold},
        "tool_version": TOOL_VERSION,
    }
