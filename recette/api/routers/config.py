"""U1/U4: config CRUD endpoints (Lane B agents + AI backends + servers).

B5 adds server lifecycle routes (start/stop/status) and the access-log tail.
Failure mode (fail-safe): the declared_url reachability probe maps every
network failure to {"status": "down"} -- it never raises to the client.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request, Response

from ...llm import Message, build_llm
from ...platform.events import PlatformActionEvent
from ...platform.netname.resolver import ResolutionDenied, resolve_name
from ...platform.proxy.lab_proxy import LabHttpProxy
from ...platform.proxy.router import resolve_proxy
from ..config_store import ServerNetnameError, UnknownAgentError, UnknownServerError
from ..server_manager import ServerManager

router = APIRouter(prefix="/config", tags=["config"])

# One short reachability probe per status request; the console polls, so a
# slow upstream must not pin the worker (R5: keep the knob in one place).
_PROBE_TIMEOUT_S = 2.0

# Module-level singleton so the Body() call is not evaluated per-signature
# (ruff B008); FastAPI resolves it identically.
_OPTIONAL_JSON_BODY = Body(default=None)

# Single source of truth (R5): provider -> env var holding its API key (R8).
# Mirrors the ENV_KEY constants on the provider classes in recette.llm.
# openai_compat is absent on purpose: its key is optional (keyless local
# servers), so its key is always considered configured.
_PROVIDER_ENV_KEY = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "xai": "XAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "together": "TOGETHER_API_KEY",
    "fireworks": "FIREWORKS_API_KEY",
    "moonshot": "KIMI_API_KEY",
    "zai": "GLM_API_KEY",
    "zai_coding": "GLM_API_KEY",
    "dashscope": "DASHSCOPE_API_KEY",
    "nvidia": "NVIDIA_API_KEY",
    "nous": "NOUS_API_KEY",
    "ollama_cloud": "OLLAMA_API_KEY",
    "novita": "NOVITA_API_KEY",
    "stepfun": "STEPFUN_API_KEY",
    "arcee": "ARCEEAI_API_KEY",
    "xiaomi": "XIAOMI_API_KEY",
    "gmi": "GMI_API_KEY",
    "huggingface": "HF_TOKEN",
    "minimax": "MINIMAX_API_KEY",
    "minimax_cn": "MINIMAX_CN_API_KEY",
    "opencode_zen": "OPENCODE_ZEN_API_KEY",
    "kilocode": "KILOCODE_API_KEY",
    "alibaba_coding_plan": "ALIBABA_CODING_PLAN_API_KEY",
    "qwen": "QWEN_API_KEY",
    "cerebras": "CEREBRAS_API_KEY",
    "skynet": "SKYNET_API_KEY",
    # "internal" is a neutral display name for the same internal vLLM gateway:
    # it resolves identically (same key/env). The prior id keeps working; new
    # backends can be created as "internal".
    "internal": "SKYNET_API_KEY",
    "bedrock": "AWS_BEARER_TOKEN_BEDROCK",
}

# Providers that take a base_url alongside the key. "required" means the backend
# cannot resolve without it (openai_compat: the host IS the provider); "optional"
# means it overrides a sensible default (bedrock: the region host).
# The internal gateway routes each model at its own base_url
# (api.skynet.cossi.internet/<slug>/v1). This map lets the console auto-fill
# base_url when a gateway model is picked, so the operator never hand-types the
# per-model route. Keys match the gateway's curated model list (the 6 chat-capable
# routes, verified live, R13); the two non-chat routes are absent.
_SKYNET = "https://api.skynet.cossi.internet"
_PROVIDER_MODEL_ENDPOINTS: dict[str, dict[str, str]] = {
    "skynet": {
        "openai/gpt-oss-120b": f"{_SKYNET}/gpt-oss-120b/v1",
        "Foundation-Sec-8B-Reasoning-Q4_K_M.gguf": f"{_SKYNET}/foundationsec/v1",
        "GLM-4.6V-Q4_K_M-00001-of-00002.gguf": f"{_SKYNET}/glm46v/v1",
        "gemma-4-31B-it-BF16-00001-of-00002.gguf": f"{_SKYNET}/gemma/v1",
        "qwen3.6-35b-a3b": f"{_SKYNET}/qwen3.6/v1",
        "mistralai/Voxtral-Mini-3B-2507": f"{_SKYNET}/voxtral/v1",
    },
}
# "internal" shares the same per-model endpoint map (same object) so the alias
# never drifts from the routes it points at.
_PROVIDER_MODEL_ENDPOINTS["internal"] = _PROVIDER_MODEL_ENDPOINTS["skynet"]

_PROVIDER_BASE_URL = {
    "openai_compat": "required",
    "skynet": "required",
    "internal": "required",
    "bedrock": "optional",
}


def _provider_catalog() -> list[dict]:
    """Describe every provider the console can offer, derived from the llm factory.

    The console builds its provider dropdown from this list instead of a
    hand-kept copy, so a vendor added to recette.llm._PROVIDERS (plus its env-var
    entry above) shows up in the UX with no frontend edit. Each entry carries the
    env-var hint (write-only key, R8), whether a key is required, and whether a
    base_url field applies.
    """
    from ...llm import _PROVIDERS, provider_models

    catalog: list[dict] = []
    for provider in _PROVIDERS:
        models = list(provider_models(provider))
        catalog.append(
            {
                "id": provider,
                "env_key": _PROVIDER_ENV_KEY.get(provider),
                "key_required": provider != "openai_compat",
                "base_url": _PROVIDER_BASE_URL.get(provider),
                # Known model ids for the console dropdown (first = default),
                # empty when none are curated -> the UI offers a free-text field.
                "models": models,
                "default_model": models[0] if models else None,
                # Per-model base_url map (the internal gateway routes per model); {} for the
                # rest. The console auto-fills base_url from the picked model.
                "model_endpoints": _PROVIDER_MODEL_ENDPOINTS.get(provider, {}),
            }
        )
    return catalog


def _key_configured(provider: str, backend_id: str, secret_store: Any) -> bool:
    """True if a key is resolvable: per-backend secret first, then the
    provider's env-var fallback. openai_compat needs no key, so it is always
    considered configured. The key value is never read or returned here."""
    if secret_store.is_configured(backend_id):
        return True
    if provider == "openai_compat":
        return True
    env_key = _PROVIDER_ENV_KEY.get(provider)
    return bool(env_key and os.environ.get(env_key))


def _store(request: Request):
    return request.app.state.config_store


def _secrets(request: Request):
    return request.app.state.secret_store


def _manager(request: Request):
    return request.app.state.server_manager


# Modes the ServerManager can spawn (port-bound, same mock_server process):
# mock_local (mediated lab double) and honeypot (a sink excluded from the
# reconcile allowlist). Sourced from the manager to avoid drift.
_STARTABLE_SERVER_MODES = ServerManager._STARTABLE_MODES


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
        # operator-configured declared_url reachability probe, not attacker input
        with urllib.request.urlopen(base_url, timeout=_PROBE_TIMEOUT_S):  # noqa: S310  # nosec B310
            return "up"
    except urllib.error.HTTPError:
        return "up"  # the server answered, just not with 2xx/3xx
    except (urllib.error.URLError, OSError, ValueError):
        return "down"


@router.get("/agents")
def list_agents(request: Request) -> list[dict]:
    return _store(request).read()["agents"]


@router.get("/agents/{agent_id}")
def get_agent(request: Request, agent_id: str) -> dict:
    # Single-agent fetch for the console detail/edit view: scanning the list
    # client-side is not a contract. Strict 404 on unknown id (delete route).
    agent = _store(request).get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"no agent {agent_id!r}")
    return agent


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
    # delete_agent raises on unknown id (aligned with delete_server).
    try:
        _store(request).delete_agent(agent_id)
    except UnknownAgentError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=204)


@router.get("/ai-providers")
def list_ai_providers() -> list[dict]:
    """The provider catalog that drives the console's provider dropdown.

    Single source of truth: recette.llm._PROVIDERS + the env-var map above. No
    key material is ever included -- only the env-var name as a hint (R8).
    """
    return _provider_catalog()


@router.get("/ai-backends")
def list_ai_backends(request: Request) -> list[dict]:
    """List backends, each enriched with key_configured (R8).

    key_configured is a boolean only -- the key value is NEVER included.
    It is true when a per-backend secret is stored OR the provider's env
    var is present (or the provider is openai_compat, key optional).
    """
    secret_store = _secrets(request)
    out: list[dict] = []
    for backend in _store(request).read()["ai_backends"]:
        entry = dict(backend)
        entry["key_configured"] = _key_configured(
            backend.get("provider", ""), backend.get("id", ""), secret_store
        )
        out.append(entry)
    return out


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


@router.post("/ai-backends/{backend_id}/test")
def test_ai_backend(
    request: Request, backend_id: str, body: dict | None = _OPTIONAL_JSON_BODY
) -> dict:
    """Probe / free-text prompt: one real call to the configured provider.

    The optional JSON body {"prompt": "..."} drives the call. When it is
    absent or its "prompt" is empty/whitespace, the legacy connectivity
    probe runs (system "connectivity probe", user "ping"). A non-empty
    prompt switches to a concise-assistant system prompt and sends the
    prompt as the user message. The model's text answer is always returned.

    Diagnostic path, NOT a decision path -- I4 does not apply to the
    wall-clock latency measured here. Failure mode is fail-safe: every
    error (missing key, network failure, bad base_url...) maps to
    {"ok": false, "latency_ms": ..., "error": ...}; exceptions never
    leak to the client as a 500. Unknown backend id is the only 404.
    """
    backend = _store(request).get_ai_backend(backend_id)
    if backend is None:
        raise HTTPException(status_code=404, detail=f"no ai_backend {backend_id!r}")
    prompt = ""
    if isinstance(body, dict):
        raw_prompt = body.get("prompt")
        if isinstance(raw_prompt, str) and raw_prompt.strip():
            prompt = raw_prompt
    if prompt:
        system = (
            "You are a helpful assistant for an AI-governance recette platform. Answer concisely."
        )
        user_text = prompt
    else:
        system = "You are a connectivity probe. Reply with one word."
        user_text = "ping"
    factory = getattr(request.app.state, "llm_factory", None) or build_llm
    # Per-backend secret first, then the provider's env-var fallback (R8). The
    # key is passed straight to the factory; it is never logged or returned.
    api_key = request.app.state.secret_store.get_secret(backend_id)
    t0 = time.perf_counter()
    try:
        llm = factory(
            backend["provider"],
            backend["model"],
            base_url=backend.get("base_url"),
            api_key=api_key,
        )
        decision = llm.decide(
            system=system,
            history=[Message(role="user", content=user_text)],
            tools=[],
        )
    except Exception as exc:  # noqa: BLE001 -- fail-safe diagnostic boundary
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return {"ok": False, "latency_ms": latency_ms, "error": str(exc)}
    latency_ms = int((time.perf_counter() - t0) * 1000)
    return {
        "ok": True,
        "latency_ms": latency_ms,
        "kind": decision.kind,
        "text": decision.text,
    }


@router.put("/ai-backends/{backend_id}/secret")
def set_ai_backend_secret(request: Request, backend_id: str, body: dict[str, Any]) -> dict:
    """Store the per-backend API key (R8). The key is never echoed back.

    404 if the backend id is unknown; 400 if api_key is missing/empty.
    """
    if _store(request).get_ai_backend(backend_id) is None:
        raise HTTPException(status_code=404, detail=f"no ai_backend {backend_id!r}")
    api_key = body.get("api_key")
    if not isinstance(api_key, str) or not api_key.strip():
        raise HTTPException(status_code=400, detail="api_key is required")
    _secrets(request).set_secret(backend_id, api_key)
    return {"configured": True}


@router.delete("/ai-backends/{backend_id}/secret", status_code=204)
def delete_ai_backend_secret(request: Request, backend_id: str) -> Response:
    """Remove the per-backend API key (R8). 404 if the backend is unknown."""
    if _store(request).get_ai_backend(backend_id) is None:
        raise HTTPException(status_code=404, detail=f"no ai_backend {backend_id!r}")
    _secrets(request).delete_secret(backend_id)
    return Response(status_code=204)


@router.get("/containment")
def get_containment(request: Request) -> dict:
    """Read the global private-DNS containment flag (default false)."""
    return {"containment": _store(request).containment_enabled()}


@router.put("/containment")
def set_containment(request: Request, body: dict[str, Any]) -> dict:
    """Persist the global containment flag. Body: {"enabled": bool}.

    Missing/invalid "enabled" is a 422 (semantic validation), consistent with
    FastAPI's body-validation contract elsewhere.
    """
    enabled = body.get("enabled")
    if not isinstance(enabled, bool):
        raise HTTPException(status_code=422, detail="'enabled' must be a boolean")
    _store(request).set_containment(enabled)
    return {"containment": enabled}


@router.post("/resolve")
def resolve_probe(request: Request, body: dict[str, Any]) -> dict:
    """Probe how a name resolves against the server allowlist (diagnostic).

    Body: ``{"name": str, "containment"?: bool}``. ``containment`` defaults to
    the store's global flag when absent. A DENIED probe is a successful probe
    RESULT, not an error: it returns HTTP 200 with ``resolved: false`` rather
    than surfacing ResolutionDenied to the client. Pure, diagnostic path -- no
    event is appended, the resolver stays I4-pure.
    """
    name = body.get("name")
    if not isinstance(name, str) or not name:
        raise HTTPException(status_code=422, detail="'name' must be a non-empty string")
    store = _store(request)
    raw_containment = body.get("containment")
    containment = (
        raw_containment if isinstance(raw_containment, bool) else store.containment_enabled()
    )
    servers = store.list_servers()
    try:
        entry = resolve_name(name, servers, containment=containment)
    except ResolutionDenied:
        return {"name": name, "resolved": False, "reason": "not_in_allowlist"}
    if entry is None:
        return {"name": name, "resolved": False, "reason": "unknown_legacy"}
    return {
        "name": name,
        "resolved": True,
        "server_id": entry["id"],
        "fqdn": entry.get("fqdn"),
    }


@router.get("/servers")
def list_servers(request: Request) -> list[dict]:
    return _store(request).list_servers()


@router.post("/servers", status_code=201)
def create_server(request: Request, server: dict[str, Any]) -> dict:
    try:
        return _store(request).add_server(server)
    except ServerNetnameError as exc:
        # A malformed/colliding fqdn/alias is a semantic validation failure (422),
        # distinct from a generic bad request like a duplicate id (400 below).
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/servers/{server_id}")
def update_server(request: Request, server_id: str, patch: dict[str, Any]) -> dict:
    try:
        return _store(request).update_server(server_id, patch)
    except UnknownServerError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ServerNetnameError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/servers/{server_id}", status_code=204)
def delete_server(request: Request, server_id: str) -> Response:
    # delete_server raises on unknown id (same strict 404 as delete_agent).
    try:
        _store(request).delete_server(server_id)
    except UnknownServerError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=204)


@router.post("/servers/{server_id}/start")
def start_server(request: Request, server_id: str) -> dict:
    """Start one port-bound server (mock_local or honeypot) via the manager.

    Both manager outcomes are HTTP 200: {"status": "up"} and
    {"status": "down", "error": ...} (e.g. busy port) are domain results
    the console renders, not transport errors.
    """
    server = _get_server_or_404(request, server_id)
    if server.get("mode") not in _STARTABLE_SERVER_MODES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"only modes {sorted(_STARTABLE_SERVER_MODES)} can be started, "
                f"got {server.get('mode')!r}"
            ),
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


@router.post("/servers/{server_id}/test")
def test_server(request: Request, server_id: str, body: dict | None = _OPTIONAL_JSON_BODY) -> dict:
    """Diagnostic probe: fire one action at a configured server and return its
    raw response, exactly as a run's proxy would (I5 path).

    Body: ``{"action_type": str, "resource": str, "payload": dict}``.
    ``action_type`` is required; ``resource`` defaults to "" and ``payload``
    to ``{}``. The action is sent through the SAME ExternalSystemProxy a real
    run uses (``resolve_proxy``), so a "test OK" here means the server answers
    the lab wire contract (``POST /{system}/execute`` -> ``{success, data}``).

    Diagnostic path, NOT a decision/audit path: no event is appended (I1 N/A)
    and the synthetic ``event_id``/``timestamp`` are fixed inputs, never
    generated inside a decision (I4 N/A). Fail-safe: every execution error
    (server down, transport failure, non-2xx) maps to ``{"ok": false, ...}``;
    only an unknown server id is a 404, and a non-probeable mode
    (real_saas / malformed entry) is a 400.
    """
    server = _get_server_or_404(request, server_id)
    action_type = ""
    resource = ""
    payload: dict = {}
    if isinstance(body, dict):
        raw_action = body.get("action_type")
        if isinstance(raw_action, str):
            action_type = raw_action.strip()
        raw_resource = body.get("resource")
        if isinstance(raw_resource, str):
            resource = raw_resource
        raw_payload = body.get("payload")
        if isinstance(raw_payload, dict):
            payload = raw_payload
    if not action_type:
        raise HTTPException(status_code=400, detail="action_type is required")
    try:
        # A single-entry registry: resolve_proxy validates mode/port and refuses
        # real_saas or a malformed entry (fail-safe, never the wrong target).
        proxy = resolve_proxy({"server": server_id}, [server], LabHttpProxy())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    event = PlatformActionEvent(
        event_id=f"console-test-{server_id}-{action_type}",
        timestamp="1970-01-01T00:00:00Z",
        agent_id="console-test",
        capability_scope=(),
        role="diagnostic",
        action_type=action_type,
        target_system=str(server["system"]),
        resource=resource,
        payload=payload,
        risk_score=0,
        risk_level="low",
    )
    t0 = time.perf_counter()
    try:
        result = proxy.execute(event)
    except Exception as exc:  # noqa: BLE001 -- fail-safe diagnostic boundary
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return {"ok": False, "latency_ms": latency_ms, "error": str(exc)}
    latency_ms = int((time.perf_counter() - t0) * 1000)
    return {
        "ok": result.ok,
        "latency_ms": latency_ms,
        "status_code": result.status_code,
        "response": result.response,
        "side_effect_hash": result.side_effect_hash,
        "error": result.error,
    }
