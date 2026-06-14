"""Red-team / simulation runs: frozen, replayable conversations for the console.

GET /sim/runs lists the committed runs under corpus/sim/; GET /sim/runs/{id}
returns the step-through view (transcript turns + per-turn checks + the action log
+ the four-dimension verdict). The runs are recorded artifacts -- the console
never triggers a live LLM. Deterministic (I4), read-only (I1).
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

from ...redteam_promote import promote_scenario
from ...redteam_recette import run_scenario, run_scenario_view
from ...sim_view import SimRecording, build_sim_view

router = APIRouter(prefix="/sim", tags=["sim"])

_SIM_DIR = Path(__file__).resolve().parents[3] / "corpus" / "sim"


def _discover() -> list[Path]:
    if not _SIM_DIR.is_dir():
        return []
    return sorted(_SIM_DIR.glob("*.sim.json"))


def _discover_scenarios() -> list[Path]:
    if not _SIM_DIR.is_dir():
        return []
    return sorted(_SIM_DIR.glob("*.scenario.json"))


def list_runs() -> list[dict]:
    """Pure: summarize every committed sim run."""
    runs: list[dict] = []
    for path in _discover():
        try:
            view = build_sim_view(SimRecording.load(path))
        except (ValueError, OSError, KeyError):
            continue
        runs.append(
            {
                "agent_id": view["agent_id"],
                "name": view["name"],
                "verdict": view["verdict"],
                "stopped_reason": view["stopped_reason"],
            }
        )
    return runs


def get_run(agent_id: str) -> dict | None:
    """Pure: the step-through view of one sim run, or None if absent."""
    for path in _discover():
        rec = SimRecording.load(path)
        if rec.spec.get("agent_id") == agent_id:
            return build_sim_view(rec)
    return None


def list_scenarios() -> list[dict]:
    """Pure: summarize every committed red-team scenario with its outcome.

    For each scenario file: load the raw JSON (for the human ``name``), run it
    through run_scenario, and merge the outcome (verdict, expected_verdict,
    violation_type, anomaly_caught, tags) with the name. Files that fail to
    load/validate/replay are skipped (mirrors list_runs), so one bad scenario
    never blanks the list.
    """
    scenarios: list[dict] = []
    for path in _discover_scenarios():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            outcome = run_scenario(data)
        except (ValueError, OSError, KeyError, json.JSONDecodeError):
            continue
        scenarios.append(
            {
                "scenario_id": outcome.scenario_id,
                "name": data.get("name", outcome.scenario_id),
                "verdict": outcome.verdict,
                "expected_verdict": outcome.expected_verdict,
                "violation_type": outcome.violation_type,
                "anomaly_caught": outcome.anomaly_caught,
                "tags": outcome.tags,
            }
        )
    return scenarios


def get_scenario(scenario_id: str) -> dict | None:
    """Pure: the step-through view of one scenario (outcome + transcript), or None.

    Returns None only for a genuinely-unknown ``scenario_id`` (no matching file,
    or files unreadable). When the matching file IS present but malformed (valid
    JSON failing schema/replay), ``run_scenario_view`` raises ``ValueError`` and
    we let it propagate so the route handler can surface an explicit 422 -- a
    present-but-invalid scenario must be legible, not a bare 500.
    """
    for path in _discover_scenarios():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("scenario_id") == scenario_id:
            return run_scenario_view(data)
    return None


@router.get("/runs")
def runs() -> dict:
    """List every committed red-team / simulation run with its verdict."""
    items = list_runs()
    return {"count": len(items), "runs": items}


@router.get("/runs/{agent_id}")
def run_view(agent_id: str) -> dict:
    """Step-through view of one recorded run."""
    view = get_run(agent_id)
    if view is None:
        raise HTTPException(status_code=404, detail=f"no sim run {agent_id!r}")
    return view


@router.get("/scenarios")
def scenarios() -> dict:
    """List every red-team scenario with its verdict and whether it was caught."""
    items = list_scenarios()
    return {"count": len(items), "scenarios": items}


@router.get("/scenarios/{scenario_id}")
def scenario_view(scenario_id: str) -> dict:
    """Step-through view of one scenario: outcome + replayed transcript.

    Unknown ``scenario_id`` (no matching file) -> 404. A present-but-malformed
    scenario file (valid JSON failing schema/replay) -> 422 with the validation
    message, instead of leaking a bare 500 (legibility-first).
    """
    try:
        view = get_scenario(scenario_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if view is None:
        raise HTTPException(status_code=404, detail=f"no scenario {scenario_id!r}")
    return view


@router.post("/scenarios/{scenario_id}/promote")
def promote(scenario_id: str, overwrite: bool = False) -> dict:
    """Freeze a caught anomaly (verdict=incorrect, single-axis) into a negative
    corpus subject, closing the recette loop.

    Returns ``{slug, created, verdict, violation_type}``. Error mapping
    (legibility-first): an unknown scenario id -> 404; a true-negative scenario
    or a multi-axis run that cannot be frozen single-axis -> 422 with the reason;
    an already-promoted subject (without ?overwrite=true) -> 409.
    """
    try:
        return promote_scenario(scenario_id, overwrite=overwrite)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        message = str(exc)
        if message.startswith("unknown scenario id"):
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=422, detail=message) from exc
