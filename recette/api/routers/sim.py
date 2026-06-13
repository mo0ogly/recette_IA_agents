"""Red-team / simulation runs: frozen, replayable conversations for the console.

GET /sim/runs lists the committed runs under corpus/sim/; GET /sim/runs/{id}
returns the step-through view (transcript turns + per-turn checks + the action log
+ the four-dimension verdict). The runs are recorded artifacts -- the console
never triggers a live LLM. Deterministic (I4), read-only (I1).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException

from ...sim_view import SimRecording, build_sim_view

router = APIRouter(prefix="/sim", tags=["sim"])

_SIM_DIR = Path(__file__).resolve().parents[3] / "corpus" / "sim"


def _discover() -> list[Path]:
    if not _SIM_DIR.is_dir():
        return []
    return sorted(_SIM_DIR.glob("*.sim.json"))


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
