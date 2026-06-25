"""Correlate the static discovery scan with the runtime behavioral wave.

Discovery PREDICTS risk from source; the behavioral engine MEASURES it at
runtime. correlate() joins them through the agent identity map and classifies
each agent into a 2x2 quadrant. The headline research signal is ``static_blind``
-- a source the scanner called clean that behaves dirty at runtime.

Pure (I4): a function of (discovery_facts, behavior_reports, links, thresholds);
no clock, no random, sorted/stable output -> byte-identical on replay.
"""

from __future__ import annotations

from pathlib import Path

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
        "agree_dirty": [],
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
        # behavioral_score = 100 - penalties: a LOWER score means MORE findings
        # (dirtier behaviour), so runtime_dirty = score strictly below the threshold.
        runtime_dirty = int(beh.get("behavioral_score", 0)) < dirty_threshold
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
        if quadrant == "agree_clean":
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


def build_discovery_facts(
    links: list[Link],
    corpus_root: Path | str | None = None,
) -> dict[str, dict]:
    """Run the reference source-scan adapter over each link's discovery subject
    and reduce it to {detected, flagged}.

    Surface-aware: each link's surface field (default "github") selects the
    corpus sub-directory via SURFACE_CORPUS. This lets github (corpus/repos)
    and gitlab (corpus/gitlab) subjects coexist in the same scan.

    flagged uses the invariant risk LEVEL (never an opaque score), per the
    discovery ground-truth rule: flagged = detected AND max_level strictly
    above the lower median of detected levels across ALL detected linked
    subjects across both surfaces.
    The lower median (index (n-1)//2 of the sorted list) avoids a bias where
    a two-element set [low, high] would raise the median to high, making
    nothing flaggable. The adapter scan is deterministic (proven in
    discovery_harness), so this function is deterministic given the corpus.
    Returns a dict sorted by key (I4).
    """
    from ..adapters import ReferenceSourceScanAdapter
    from ..discovery_harness import SURFACE_CORPUS, _max_level

    adapter = ReferenceSourceScanAdapter()
    facts: dict[str, dict] = {}
    levels: dict[str, int] = {}

    for ln in sorted(links, key=lambda x: x.agent_id):
        subj = ln.discovery_subject
        if not subj or subj in facts:
            continue
        surface = ln.surface or "github"
        if corpus_root is not None:
            # caller-supplied root: resolve directly (used in tests)
            surface_root = Path(corpus_root)
        else:
            surface_root = SURFACE_CORPUS.get(surface, SURFACE_CORPUS["github"])
        repo_tree = surface_root / subj / "repo"
        if not repo_tree.exists():
            facts[subj] = {"detected": False, "flagged": False}
            continue
        sid = adapter.register(str(repo_tree))
        adapter.await_run(adapter.scan(sid))
        risks = adapter.risks(sid)
        detected = len(risks) > 0
        facts[subj] = {"detected": detected}
        if detected:
            levels[subj] = _max_level(risks)

    # flagged = detected AND max level strictly above the lower median of all
    # detected levels across ALL surfaces in the scanned set (invariant:
    # relative risk ordering, never an absolute score).
    detected_levels = sorted(levels.values())
    median = detected_levels[(len(detected_levels) - 1) // 2] if detected_levels else 0
    for subj in facts:
        facts[subj]["flagged"] = facts[subj]["detected"] and levels.get(subj, 0) > median

    return dict(sorted(facts.items()))


def correlate_corpus(
    links: list[Link],
    thresholds: dict,
    corpus_root: Path | str | None = None,
) -> dict:
    """Populate quadrants from frozen twin bundles -- no live probe.

    For each link with an evidence_bundle, load ``<evidence_bundle>/bundle.json``
    relative to the repo root (or ``corpus_root`` when supplied), run one wave with
    the default exfil profile, and take the agent's report into behavior_reports.
    Then delegates to the pure ``correlate``.  Deterministic (I4): twin bundles are
    frozen fixtures; no clock/random in the wave engine.
    """
    import json as _json

    from . import EvidenceBundle
    from .engine import run_wave
    from .profile import AnalysisProfile

    facts = build_discovery_facts(links, corpus_root)
    behavior_reports: dict[str, dict] = {}
    prof = AnalysisProfile.from_dict({"threat": "exfil"})

    # resolve the repo root once (evidence_bundle paths in agent_links.json are repo-relative)
    if corpus_root is not None:
        root = Path(corpus_root)
    else:
        # DEFAULT_LINKS lives at <repo_root>/corpus/agent_links.json so the repo root
        # is two parents up from that file, which equals the package parents[2].
        from .links import DEFAULT_LINKS

        root = DEFAULT_LINKS.parents[1]  # corpus/ -> repo root

    for ln in links:
        if not ln.evidence_bundle:
            continue
        bpath = root / ln.evidence_bundle / "bundle.json"
        if not bpath.exists():
            continue
        data = _json.loads(bpath.read_text(encoding="utf-8"))
        rep = run_wave(EvidenceBundle.from_dict(data), prof).to_dict()
        for a in rep["agents"]:
            if a["agent_id"] == ln.agent_id:
                behavior_reports[ln.agent_id] = a

    return correlate(facts, behavior_reports, links, thresholds)


def discovery_cohort(links, mode, corpus_root=None):
    """Resolve a wave cohort from a discovery scan: the agent_ids whose
    discovery_subject is detected (mode="detected") or flagged (mode="flagged").
    Pure given the corpus (build_discovery_facts is deterministic); sorted+deduped
    so the cohort is byte-stable across runs (I4)."""
    if mode not in ("detected", "flagged"):
        raise ValueError(f"unknown cohort mode: {mode!r} (expected detected|flagged)")
    facts = build_discovery_facts(links, corpus_root)
    out = set()
    for ln in links:
        subj = ln.discovery_subject
        fact = facts.get(subj or "")
        if fact and fact.get(mode if mode == "detected" else "flagged"):
            out.add(ln.agent_id)
    return sorted(out)
