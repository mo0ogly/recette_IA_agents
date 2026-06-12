"""U1: GET /agents catalog router."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..catalog import build_catalog

router = APIRouter(tags=["catalog"])


@router.get("/agents")
def get_catalog(request: Request) -> dict:
    return build_catalog(request.app.state.config_store)
