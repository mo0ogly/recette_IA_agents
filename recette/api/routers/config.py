"""U1/U4: config CRUD endpoints (Lane B agents + AI backends + servers).

B5 adds server lifecycle routes (start/stop/status) and the access-log tail.
Failure mode (fail-safe): the declared_url reachability probe maps every
network failure to {"status": "down"} -- it never raises to the client.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response

from ..config_store import UnknownAgentError, UnknownServerError

router = APIRouter(prefix="/config", tags=["config"])

# One short reachability probe per status request; the console polls, so a
# slow upstream must not pin the worker (R5: keep the knob in one place).
_PROBE_TIMEOUT_S = 2.0


def _store(request: Request):
    return request.app.state.config_store


def _manager(request: Request):
    return request.app.state.server_manager


def _get_server_or_404(request: Request, server_id: str) -> dict:
    server = _store(request).get_server(server_id)
    if server is None:
        raise HTTPException(status_code=404, detail=f"no server {server_id!r}")
    return server


def _probe_base_url(base_url: str) -> str:
    """One GET reachability probe: any HTTP answer (even 4xx/5xx) is "up".

    Fail-safe: connection errors, timeouts and malformed URLs all map to
    "down"; the probe never raises to the client. Only http(s) schemes are
    probed -- anything else (e.g. file://) is "down", never opened.
    """
    if not base_url.startswith(("http://", "https://")):
        return "down"
    try:
        with urllib.request.urlopen(base_url, timeout=_PROBE_TIMEOUT_S):
            return "up"
    except urllib.error.HTTPError:
        return "up"  # the server answered, just not with 2xx/3xx
    except (urllib.error.URLError, OSError, ValueError):
        return "down"


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


@router.post("/servers/{server_id}/start")
def start_server(request: Request, server_id: str) -> dict:
    """Start one mock_local server via the manager.

    Both manager outcomes are HTTP 200: {"status": "up"} and
    {"status": "down", "error": ...} (e.g. busy port) are domain results
    the console renders, not transport errors.
    """
    server = _get_server_or_404(request, server_id)
    if server.get("mode") != "mock_local":
        raise HTTPException(
            status_code=400,
            detail=f"only mode 'mock_local' servers can be started, got {server.get('mode')!r}",
        )
    try:
        return _manager(request).start(server)
    except ValueError as exc:
        # Defense in depth: the manager re-validates the entry (mode, port).
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/servers/{server_id}/stop")
def stop_server(request: Request, server_id: str) -> dict:
    _get_server_or_404(request, server_id)
    return _manager(request).stop(server_id)


@router.get("/servers/{server_id}/status")
def server_status(request: Request, server_id: str) -> dict:
    """Live status per mode: process poll, URL probe, or n/a (real_saas)."""
    server = _get_server_or_404(request, server_id)
    mode = server.get("mode")
    if mode == "mock_local":
        return {"status": _manager(request).status(server_id)}
    if mode == "declared_url":
        return {"status": _probe_base_url(server.get("base_url", ""))}
    return {"status": "n/a"}


@router.get("/servers/{server_id}/log")
def server_log(request: Request, server_id: str, after: int = 0) -> dict:
    """Incremental tail of the server's JSONL access log.

    Returns the parsed entries from index ``after`` onward plus ``next``,
    the cursor the console passes back on its next poll. A missing file is
    an empty tail, not an error. A malformed trailing line (partial write
    by the server process) stops the read; it is picked up on the next poll
    because ``next`` only counts fully parsed entries.
    """
    _get_server_or_404(request, server_id)
    after = max(after, 0)
    log_path = _manager(request).access_log_path(server_id)
    if not log_path.exists():
        return {"lines": [], "next": after}
    entries: list[Any] = []
    with log_path.open(encoding="utf-8") as fh:
        for raw_line in fh:
            stripped = raw_line.strip()
            if not stripped:
                continue
            try:
                entries.append(json.loads(stripped))
            except json.JSONDecodeError:
                break
    return {"lines": entries[after:], "next": len(entries)}
