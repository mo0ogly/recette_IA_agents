"""U1: GET /agents catalog router."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ..catalog import build_catalog

router = APIRouter(tags=["catalog"])


@router.get("/agents")
def get_catalog(request: Request) -> dict:
    return build_catalog(request.app.state.config_store)


@router.post("/agents/register", status_code=201)
def register_agent(request: Request, agent: dict[str, Any]) -> dict:
    try:
        return request.app.state.config_store.add_agent(agent)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
