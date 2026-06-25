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


@router.post("/wave")
def wave(request: Request, body: dict[str, Any]) -> dict:
    """Run one wave. Body: ``{"recording": {...}, "profile": {...},
    "ground_truth": {...}?}``. Returns ``{"report": ..., "metrics": ...|null}``.
    400 on a missing recording or an invalid profile."""
    recording = body.get("recording")
    if not isinstance(recording, dict):
        raise HTTPException(status_code=400, detail="recording (object) is required")
    try:
        profile = AnalysisProfile.from_dict(body.get("profile") or {})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid profile: {exc}") from exc

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
    return {"report": report.to_dict(), "metrics": metrics}


@router.post("/correlate")
def correlate_endpoint(request: Request, body: dict[str, Any]) -> dict:
    """Run a wave then correlate its behavioral reports with the static discovery
    scan through the agent identity map. Returns the quadrant report alongside
    the raw wave report.

    Body: ``{"recording": {...}, "profile": {...}, "thresholds": {...}?}``
    Returns: ``{"report": ..., "correlation": {...}}``.
    400 on a missing recording or an invalid profile (same contract as /wave).
    """
    from ...behavior.correlate import build_discovery_facts, correlate
    from ...behavior.links import load_links

    recording = body.get("recording")
    if not isinstance(recording, dict):
        raise HTTPException(status_code=400, detail="recording (object) is required")
    try:
        profile = AnalysisProfile.from_dict(body.get("profile") or {})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid profile: {exc}") from exc

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
    links = load_links()
    discovery_facts = build_discovery_facts(links)
    thresholds = body.get("thresholds") or {"runtime_dirty": 50}
    corr = correlate(discovery_facts, behavior_reports, links, thresholds)
    return {"report": report.to_dict(), "correlation": corr}
