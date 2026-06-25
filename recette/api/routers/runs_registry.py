"""GET/POST/PATCH/DELETE/POST endpoints for the eurodated run registry.

Prefix: /results  (RAW JSON, no {success,data} envelope -- R16, client.ts)

The registry root resolves from env INSPECT_IA_AGENTS_RUNS_ROOT or the repo
default docs/tracking/runs/ (R5).  Path-traversal is guarded: any artifact
name that escapes the run's artifacts dir -> 400.  Replay dispatch is by
run kind; kinds without a replayer return 422 "not replayable".
"""

from __future__ import annotations

import datetime
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from ...runs.registry import RunRegistry

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/results", tags=["results"])


def _registry(request: Request) -> RunRegistry:
    """Resolve the registry from app.state or the env-default (R5)."""
    reg = getattr(request.app.state, "runs_registry", None)
    if reg is not None:
        return reg  # type: ignore[return-value]
    return RunRegistry()


# ---------------------------------------------------------------------------
# Read endpoints
# ---------------------------------------------------------------------------


@router.get("/tree")
def get_tree(request: Request) -> dict:
    """Return the full category > group > run tree.  No filter; cheap dir walk."""
    return _registry(request).tree()


@router.get("/{run_id}")
def get_run(run_id: str, request: Request) -> dict:
    """Return meta + annotations + artifact list for a run."""
    try:
        return _registry(request).read_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"run {run_id!r} not found") from exc


@router.get("/{run_id}/artifact/{name:path}")
def get_artifact(run_id: str, name: str, request: Request) -> PlainTextResponse:
    """Return raw artifact content.  Guarded against path traversal -> 400."""
    reg = _registry(request)
    ref = reg.find_run(run_id)
    if ref is None:
        raise HTTPException(status_code=404, detail=f"run {run_id!r} not found")
    try:
        content = reg.read_artifact(ref, name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PlainTextResponse(content)


# ---------------------------------------------------------------------------
# Write endpoints
# ---------------------------------------------------------------------------


@router.post("", status_code=201)
def register_run(request: Request, body: dict) -> dict:
    """Register a new run (create group if needed, create run, optionally seal).

    Expected body:
      category   str
      group_id   str
      label      str   (group label)
      run_id     str
      kind       str
      eurodate   str   (injected by caller; never generated here -- I4)
      artifacts  dict[str, str]   name -> content  (optional)
      seal       bool             whether to seal immediately (default false)
    """
    category = body.get("category", "")
    group_id = body.get("group_id", "")
    label = body.get("label", "")
    run_id = body.get("run_id", "")
    kind = body.get("kind", "")
    eurodate = body.get("eurodate", "")

    if not all([category, group_id, run_id, kind, eurodate]):
        raise HTTPException(
            status_code=400,
            detail="category, group_id, run_id, kind, eurodate are required",
        )

    reg = _registry(request)
    g = reg.new_group(
        category=category,
        group_id=group_id,
        eurodate=eurodate,
        label=label,
    )
    r = reg.new_run(group=g, run_id=run_id, kind=kind, eurodate=eurodate)

    for name, content in (body.get("artifacts") or {}).items():
        try:
            reg.write_artifact(r, name, content)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    if body.get("seal", False):
        meta = reg.seal(r)
        return {"run_id": run_id, "status": "sealed", "root_hash": meta.get("root_hash")}

    return {"run_id": run_id, "status": "running"}


@router.patch("/{run_id}")
def patch_annotations(run_id: str, request: Request, body: dict) -> dict:
    """Update annotations.json for a run.  Only annotations are mutated (I1-style)."""
    reg = _registry(request)
    try:
        ann = reg.annotate(
            run_id,
            tags=body.get("tags"),
            comment=body.get("comment"),
            label=body.get("label"),
            retention=body.get("retention"),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"run {run_id!r} not found") from exc
    return ann


@router.delete("/{run_id}")
def delete_run(run_id: str, request: Request, confirm: bool = False) -> dict:
    """Archive then purge a run dir.  Requires ?confirm=true (guard against accidents)."""
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="pass ?confirm=true to confirm permanent archive + purge",
        )
    reg = _registry(request)
    try:
        archive_path = reg.delete(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"run {run_id!r} not found") from exc
    return {"run_id": run_id, "archived_to": str(archive_path), "status": "purged"}


# Replay dispatch table by run kind.
# Kinds listed here have real replayer implementations; the others return 422.
_REPLAYABLE_KINDS: frozenset[str] = frozenset(
    {
        "agent",  # recette agent replay (ReplayLlm, no key)
        "campaign",  # govscore recompute
        "recette-full",  # govscore recompute
    }
)


@router.post("/{run_id}/replay", status_code=201)
def replay_run(run_id: str, request: Request, body: dict | None = None) -> dict:
    """Spawn a new child run linked to *run_id* via meta.replay_of.

    Dispatch is by run kind.  Kinds without a real replayer return 422 (not
    replayable) -- never a fake replay.  The parent run is never mutated (I1).
    """
    reg = _registry(request)
    ref = reg.find_run(run_id)
    if ref is None:
        raise HTTPException(status_code=404, detail=f"run {run_id!r} not found")

    import json as _json

    parent_meta: dict = _json.loads((ref.path / "meta.json").read_text(encoding="utf-8"))
    kind = parent_meta.get("kind", "")

    if kind not in _REPLAYABLE_KINDS:
        raise HTTPException(
            status_code=422,
            detail=f"run kind {kind!r} is not replayable",
        )

    # Eurodate for the child: passed in body or fall back to an ops timestamp
    # (operational metadata, not a decision path -- I4 governs decision paths).
    body = body or {}
    child_eurodate: str = body.get("eurodate", "") or _ops_eurodate()

    child_ref = reg.spawn_replay(run_id, eurodate=child_eurodate)
    return {
        "child_run_id": child_ref.run_id,
        "replay_of": run_id,
        "status": "running",
        "kind": kind,
    }


def _ops_eurodate() -> str:
    """Operational timestamp for child run naming (not a decision path -- I4)."""
    return datetime.datetime.now(tz=datetime.UTC).strftime("%Y-%m-%dT%H-%M-%S")
