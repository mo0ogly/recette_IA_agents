"""POST /behavior/wave -- run a behavioral-analysis wave from the console.

The analyst sends a recording (an eBPF capture) + an AnalysisProfile (the four
knobs); the API assembles the evidence bundle from the live server registry +
each agent's declared plan (capability_scope, bound server, scenario => SAID), runs
the deterministic wave, and returns the report (+ metrics when ground-truth labels
are supplied). Pure/fail-safe: the engine has no clock/random/IO, the API holds no
privilege, and a bad profile is a friendly 400 -- never a fabricated report.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ...behavior import AnalysisProfile, EvidenceBundle
from ...behavior import metrics as M
from ...behavior.engine import run_wave
from ...surface.agent_analysis import declared_view

router = APIRouter(prefix="/behavior", tags=["behavior"])


def _declared_for(recording: dict, store: Any) -> dict[str, dict]:
    """Build ``agent_id -> declared_view`` for every agent in the recording, from
    the live config store (the same PLANNED/SAID derivation the probe path uses)."""
    out: dict[str, dict] = {}
    for rec in recording.get("recordings", []) or []:
        agent_id = str(rec.get("agent_id") or "")
        if agent_id:
            out[agent_id] = declared_view(store.get_agent(agent_id) or {})
    return out


@router.get("/profile/defaults")
def profile_defaults() -> dict:
    """The catalog the console needs to build a profile: the known lenses, the
    threat hypotheses, and the default thresholds. Static, deterministic."""
    from ...behavior.profile import ALL_LENSES, DEFAULT_THRESHOLDS, THREAT_WEIGHTS

    return {
        "lenses": list(ALL_LENSES),
        "threats": sorted(THREAT_WEIGHTS),
        "default_thresholds": DEFAULT_THRESHOLDS,
    }


def _resolve_cohort_discovery(profile: AnalysisProfile) -> dict:
    """Resolve ``profile.cohort.discovery`` into ``cohort.agents``.

    If the ``discovery`` key is present in the cohort dict, the agent_ids are
    derived from the discovery scan (``detected`` or ``flagged`` mode).  The
    profile's ``cohort["agents"]`` is updated in place so the engine filters on
    the resolved set.  Returns the cohort echo dict ``{mode, agents}`` that is
    included in every response (fail-loud: the caller always sees which cohort
    was applied).

    Imports are local so the module remains importable without the behavior
    extras installed.
    """
    cohort_echo: dict = {"mode": None, "agents": profile.cohort.get("agents", ["*"])}
    mode = profile.cohort.get("discovery")
    if not mode:
        return cohort_echo
    if mode not in ("detected", "flagged"):
        raise HTTPException(
            status_code=400,
            detail=f"invalid cohort.discovery: {mode!r} (expected detected|flagged)",
        )
    from ...behavior.correlate import discovery_cohort
    from ...behavior.links import load_links

    agents = discovery_cohort(load_links(), mode)
    profile.cohort["agents"] = agents
    cohort_echo = {"mode": mode, "agents": agents}
    return cohort_echo


@router.post("/wave")
def wave(request: Request, body: dict[str, Any]) -> dict:
    """Run one wave. Body: ``{"recording": {...}, "profile": {...},
    "ground_truth": {...}?}``. Returns ``{"report": ..., "metrics": ...|null,
    "cohort": {"mode": ..., "agents": [...]}}``.
    400 on a missing recording, an invalid profile, or an unknown cohort.discovery mode."""
    recording = body.get("recording")
    if not isinstance(recording, dict):
        raise HTTPException(status_code=400, detail="recording (object) is required")
    try:
        profile = AnalysisProfile.from_dict(body.get("profile") or {})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid profile: {exc}") from exc

    cohort_echo = _resolve_cohort_discovery(profile)

    store = request.app.state.config_store
    ground_truth = body.get("ground_truth") or {}
    bundle = EvidenceBundle.from_dict(
        {
            "recording": recording,
            "servers": store.list_servers(),
            "declared": _declared_for(recording, store),
            "ground_truth": ground_truth if isinstance(ground_truth, dict) else {},
        }
    )
    report = run_wave(bundle, profile)
    metrics = None
    if bundle.ground_truth:
        metrics = {
            "confusion": M.confusion(report, bundle.ground_truth),
            "separation_auc": M.separation_auc(report, bundle.ground_truth),
            "roc": M.roc_curve(report, bundle.ground_truth),
            "standards_distribution": M.standards_distribution(report),
        }
    return {"report": report.to_dict(), "metrics": metrics, "cohort": cohort_echo}


@router.post("/correlate")
def correlate_endpoint(request: Request, body: dict[str, Any]) -> dict:
    """Run a correlation between the static discovery scan and the behavioral engine.

    Two modes:
    - **corpus mode** (no recording): load frozen twin bundles, run each wave, then
      classify.  Body: ``{"profile": {...}?, "thresholds": {...}?}``.
      Returns ``{"correlation": {...}}``.
    - **live mode** (recording present): run a wave over the supplied recording, then
      correlate.  Body: ``{"recording": {...}, "profile": {...}?, "thresholds": {...}?}``.
      Returns ``{"report": ..., "correlation": {...}, "cohort": {"mode": ..., "agents": [...]}}``.

    400 on an invalid profile or an unknown cohort.discovery mode.
    """
    from ...behavior.links import load_links

    recording = body.get("recording")
    thresholds = body.get("thresholds") or {"runtime_dirty": 50}
    try:
        profile = AnalysisProfile.from_dict(body.get("profile") or {})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid profile: {exc}") from exc

    links = load_links()

    if not recording:
        # Corpus mode: no live recording -- load frozen twins and run waves offline.
        from ...behavior.correlate import correlate_corpus

        corr = correlate_corpus(links, thresholds)
        return {"correlation": corr}

    # Live mode: recording supplied -- run wave then correlate.
    if not isinstance(recording, dict):
        raise HTTPException(status_code=400, detail="recording must be an object")

    cohort_echo = _resolve_cohort_discovery(profile)

    store = request.app.state.config_store
    bundle = EvidenceBundle.from_dict(
        {
            "recording": recording,
            "servers": store.list_servers(),
            "declared": _declared_for(recording, store),
            "ground_truth": {},
        }
    )
    report = run_wave(bundle, profile)
    behavior_reports = {a["agent_id"]: a for a in report.to_dict()["agents"]}
    from ...behavior.correlate import build_discovery_facts, correlate

    discovery_facts = build_discovery_facts(links)
    corr = correlate(discovery_facts, behavior_reports, links, thresholds)
    return {"report": report.to_dict(), "correlation": corr, "cohort": cohort_echo}
