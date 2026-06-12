"""A1: read-only view of the governed action catalog (catalog is data, not code)."""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(prefix="/catalog", tags=["catalog-actions"])


@router.get("/actions")
def list_actions(request: Request, target_system: str | None = None) -> dict:
    specs = request.app.state.catalog.all()
    if target_system is not None:
        specs = tuple(s for s in specs if s.target_system == target_system)
    return {"actions": [s.to_dict() for s in specs], "count": len(specs)}
