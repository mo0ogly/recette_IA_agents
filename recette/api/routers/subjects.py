"""Unified subject catalog: the merged git + MAF corpus exposed to the console.

After the fusion a subject is one manifest with a ``kind`` discriminator
(git_agent | maf_agent). GET /subjects lists both families from the on-disk
corpus; GET /subjects/scorecard returns the aggregate recette verdict
(identification + MAF + discovery) the console renders as one dashboard.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

from ...harness import discover_agent_dirs
from ...maf_harness import discover_maf_dirs
from ...maf_orchestration_harness import discover_orchestration_dirs
from ...manifest import load_manifest, load_validated

router = APIRouter(prefix="/subjects", tags=["subjects"])


def _read_ground_truth(d: Path) -> dict:
    path = d / "ground-truth.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def _summarize(manifest: dict, ground_truth: dict, manifest_file: str) -> dict:
    return {
        "agent_id": manifest.get("agent_id"),
        "name": manifest.get("name"),
        "family": manifest.get("kind", "git_agent"),
        "target_systems": manifest.get("target_systems", []),
        "manifest_file": manifest_file,
        "category": ground_truth.get("category"),
        "violation_type": ground_truth.get("violation_type"),
        "expected_verdict": ground_truth.get("expected_verdict"),
    }


def _collect() -> list[dict]:
    subjects: list[dict] = []
    for d in discover_agent_dirs():
        try:
            manifest = load_manifest(d / "manifest.json")
        except (ValueError, FileNotFoundError):
            continue
        subjects.append(_summarize(manifest, _read_ground_truth(d), "manifest.json"))
    for d in discover_maf_dirs():
        try:
            manifest = load_manifest(d / "spec.json")
        except (ValueError, FileNotFoundError):
            continue
        subjects.append(_summarize(manifest, _read_ground_truth(d), "spec.json"))
    for d in discover_orchestration_dirs():
        try:
            team = load_validated("maf_orchestration", d / "team.json")
        except (ValueError, FileNotFoundError):
            continue
        subjects.append(_summarize_orchestration(team, _read_ground_truth(d)))
    return subjects


def _summarize_orchestration(team: dict, ground_truth: dict) -> dict:
    """Summarize a handoff team: its participants stand in for target_systems."""
    return {
        "agent_id": team.get("agent_id"),
        "name": team.get("name"),
        "family": "maf_orchestration",
        "target_systems": [p["agent_id"] for p in team.get("participants", [])],
        "manifest_file": "team.json",
        "category": ground_truth.get("category"),
        "violation_type": ground_truth.get("violation_type"),
        "expected_verdict": ground_truth.get("expected_verdict"),
    }


@router.get("")
def list_subjects() -> dict:
    """List every corpus subject across both families, with its ground-truth posture."""
    subjects = _collect()
    families: dict[str, int] = {}
    for s in subjects:
        families[s["family"]] = families.get(s["family"], 0) + 1
    return {"count": len(subjects), "families": families, "subjects": subjects}


@router.get("/scorecard")
def scorecard() -> dict:
    """Aggregate recette verdict over the unified corpus (identification + MAF + discovery)."""
    from ...report import build_report

    return build_report().to_dict()


def build_orchestration_view(agent_id: str) -> dict | None:
    """Pure: find the orchestration corpus subject and build its step-through view."""
    from ...maf_orchestration import run_from_doc
    from ...run_view import build_run_view

    for d in discover_orchestration_dirs():
        if d.name != agent_id:
            continue
        team = load_validated("maf_orchestration", d / "team.json")
        run = run_from_doc(load_validated("maf_orchestration_run", d / "run.json"))
        return build_run_view(team, run)
    return None


@router.get("/orchestration/{agent_id}")
def orchestration_view(agent_id: str) -> dict:
    """Step-through view of an orchestration subject: timeline + verdict + diagram."""
    view = build_orchestration_view(agent_id)
    if view is None:
        raise HTTPException(status_code=404, detail=f"no orchestration subject {agent_id!r}")
    return view


def build_orchestration_graph(agent_id: str) -> dict | None:
    """Pure: the directed interaction graph + graph metrics of an orchestration
    subject's run, or None when the subject is unknown."""
    from ...maf_orchestration import run_from_doc
    from ...orchestration_graph import interaction_graph

    for d in discover_orchestration_dirs():
        if d.name != agent_id:
            continue
        run = run_from_doc(load_validated("maf_orchestration_run", d / "run.json"))
        return interaction_graph(run)
    return None


@router.get("/orchestration/{agent_id}/graph")
def orchestration_graph(agent_id: str) -> dict:
    """The interaction graph (nodes + weighted edges) + per-node graph metrics
    (in/out degree, tool calls, weighted PageRank) of an orchestration run."""
    graph = build_orchestration_graph(agent_id)
    if graph is None:
        raise HTTPException(status_code=404, detail=f"no orchestration subject {agent_id!r}")
    return graph


@router.get("/benchmark")
def benchmark() -> dict:
    """Judge-accuracy benchmark per dimension / style / area over the corpus."""
    from ...benchmark import full_benchmark

    return full_benchmark()


def find_subject_detail(agent_id: str) -> dict | None:
    """Pure: the full manifest + ground-truth of one corpus subject, by agent_id.

    Scans the git and MAF subject dirs (manifest.json / spec.json) and the
    orchestration teams (team.json), returning the FIRST whose declared
    ``agent_id`` matches. None when no subject carries that id."""
    sources = (
        (discover_agent_dirs(), "manifest.json"),
        (discover_maf_dirs(), "spec.json"),
        (discover_orchestration_dirs(), "team.json"),
    )
    for dirs, manifest_file in sources:
        for d in dirs:
            try:
                manifest = load_manifest(d / manifest_file)
            except (ValueError, FileNotFoundError):
                continue
            if manifest.get("agent_id") != agent_id:
                continue
            return {
                "agent_id": agent_id,
                "family": manifest.get("kind", "git_agent"),
                "manifest_file": manifest_file,
                "manifest": manifest,
                "ground_truth": _read_ground_truth(d),
            }
    return None


@router.get("/{agent_id}")
def subject_detail(agent_id: str) -> dict:
    """Full manifest + ground-truth of one corpus subject (for the explain modal)."""
    detail = find_subject_detail(agent_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"no corpus subject {agent_id!r}")
    return detail
