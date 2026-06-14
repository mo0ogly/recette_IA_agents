"""Read-only HTTP surface for the on-disk recette governance campaigns.

GET /recette-campaigns        -> summaries (id, family, objective, counts)
GET /recette-campaigns/{id}   -> full document (objective, teaching, agents,
                                  actions with their expected verdict)

These never run or mutate a campaign (the CRUD campaigns live under /campaigns);
this surface only lets the console list and EXPLAIN them, mirroring the agent /
subject explain modals so every backend artifact has a UI (no orphan endpoint).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/recette-campaigns", tags=["recette-campaigns"])


def _catalog(request: Request):  # type: ignore[no-untyped-def]
    return request.app.state.recette_campaign_catalog


@router.get("")
def list_recette_campaigns(request: Request) -> dict:
    return {"campaigns": _catalog(request).list()}


@router.get("/{campaign_id}")
def get_recette_campaign(request: Request, campaign_id: str) -> dict:
    doc = _catalog(request).get(campaign_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="no such recette campaign")
    return doc
