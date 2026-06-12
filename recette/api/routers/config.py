"""U1/U4: config CRUD endpoints (Lane B agents + AI backends + servers)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response

from ..config_store import UnknownAgentError, UnknownServerError

router = APIRouter(prefix="/config", tags=["config"])


def _store(request: Request):
    return request.app.state.config_store


@router.get("/agents")
def list_agents(request: Request) -> list[dict]:
    return _store(request).read()["agents"]


@router.post("/agents", status_code=201)
def create_agent(request: Request, agent: dict[str, Any]) -> dict:
    try:
        return _store(request).add_agent(agent)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/agents/{agent_id}")
def update_agent(request: Request, agent_id: str, patch: dict[str, Any]) -> dict:
    try:
        return _store(request).update_agent(agent_id, patch)
    except UnknownAgentError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/agents/{agent_id}", status_code=204)
def delete_agent(request: Request, agent_id: str) -> Response:
    _store(request).delete_agent(agent_id)
    return Response(status_code=204)


@router.get("/ai-backends")
def list_ai_backends(request: Request) -> list[dict]:
    return _store(request).read()["ai_backends"]


@router.post("/ai-backends", status_code=201)
def create_ai_backend(request: Request, backend: dict[str, Any]) -> dict:
    try:
        return _store(request).add_ai_backend(backend)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/ai-backends/{backend_id}", status_code=204)
def delete_ai_backend(request: Request, backend_id: str) -> Response:
    _store(request).delete_ai_backend(backend_id)
    return Response(status_code=204)


@router.get("/servers")
def list_servers(request: Request) -> list[dict]:
    return _store(request).list_servers()


@router.post("/servers", status_code=201)
def create_server(request: Request, server: dict[str, Any]) -> dict:
    try:
        return _store(request).add_server(server)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/servers/{server_id}")
def update_server(request: Request, server_id: str, patch: dict[str, Any]) -> dict:
    try:
        return _store(request).update_server(server_id, patch)
    except UnknownServerError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/servers/{server_id}", status_code=204)
def delete_server(request: Request, server_id: str) -> Response:
    # delete_server raises on unknown id (unlike the idempotent delete_agent).
    try:
        _store(request).delete_server(server_id)
    except UnknownServerError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=204)
