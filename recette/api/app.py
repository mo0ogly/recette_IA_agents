"""U1/A1 app factory. Wires the routers onto a FastAPI instance.

The core recette package never imports this module -- FastAPI stays an
optional extra. A1 adds the governed-execution wiring: event store (Audit
Plane, Phase 1 SQLite), policy store, lab proxy and the Gateway (I2).
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from ..llm import build_llm
from ..platform.catalog import Catalog, load_catalog
from ..platform.eventstore import EventStore, build_event_store_from_env
from ..platform.gateway import AgentResolver, Gateway
from ..platform.policy.model import baseline_from_catalog
from ..platform.policy.store import PolicyStore
from ..platform.proxy.lab_proxy import LabHttpProxy
from ..platform.proxy.protocol import ExternalSystemProxy
from ..platform.proxy.route import registry_from_env
from ..platform.proxy.tracing import RingTraceRecorder, TracingProxy, debug_enabled_from_env
from ..platform.proxy.wire import WireFlowRecorder, wire_proxy_url_from_env
from ..platform.realtime import (
    PublishingEventStore,
    RealtimeTransport,
    build_realtime_transport_from_env,
)
from ..platform.scheduler import ScheduledTask, build_scheduler_from_env
from ..rag_store import KnowledgeBaseStore
from .auth import AuthError, decode_token, principal_from_claims
from .campaign_store import CampaignStore, RecordingStore
from .config_store import ConfigStore
from .recette_campaigns import RecetteCampaignCatalog
from .routers import actions as actions_router
from .routers import agent_actions as agent_actions_router
from .routers import approvals as approvals_router
from .routers import audit as audit_router
from .routers import campaigns as campaigns_router
from .routers import catalog as catalog_router
from .routers import catalog_actions as catalog_actions_router
from .routers import config as config_router
from .routers import discovery as discovery_router
from .routers import events as events_router
from .routers import policies as policies_router
from .routers import probe as probe_router
from .routers import proxy as proxy_router
from .routers import rag as rag_router
from .routers import recette_campaigns as recette_campaigns_router
from .routers import runs as runs_router
from .routers import sim as sim_router
from .routers import subjects as subjects_router
from .routers import verdicts as verdicts_router
from .runs import RunManager
from .secret_store import BackendSecretStore
from .server_manager import ServerManager
from .verdict_store import VerdictStore

BASELINE_POLICY_VERSION = "v1"
# Routes reachable without a token: liveness + the OpenAPI surface. Everything
# else requires a verified identity once a signing key is configured (I3).
# /events/stream is allowlisted because EventSource (browser SSE) cannot set an
# Authorization header; in a keyed deployment it must be fronted by a token-in-
# query or cookie gate (tracked residual). It only exposes a derived event tail.
AUTH_ALLOWLIST = frozenset(
    {"/health", "/openapi.json", "/docs", "/redoc", "/docs/oauth2-redirect", "/events/stream"}
)
_auth_logger = logging.getLogger("inspect_ia_agents.api.auth")


class JWTAuthMiddleware(BaseHTTPMiddleware):
    """Resolve a Principal from a Bearer JWT before any handler runs (I3).

    Enforcement is gated on configuration: when ``app.state.auth_key`` is None
    (no ``INSPECT_IA_AGENTS_JWT_SIGNING_KEY``) the API runs in open dev/test mode and a
    loud warning is logged once at startup. When a key IS set, every non-allowlisted
    route is deny-by-default: no valid token -> 401, and the failure is logged
    structured (R6) with the path and reason (never the token contents).
    """

    async def dispatch(self, request, call_next):  # type: ignore[no-untyped-def]
        key = getattr(request.app.state, "auth_key", None)
        if key is None:
            request.state.principal = None
            return await call_next(request)
        if request.method == "OPTIONS" or request.url.path in AUTH_ALLOWLIST:
            return await call_next(request)
        header = request.headers.get("authorization", "")
        token = header[7:].strip() if header[:7].lower() == "bearer " else ""
        try:
            request.state.principal = principal_from_claims(decode_token(token, key))
        except AuthError as exc:
            _auth_logger.warning(
                "auth rejected path=%s method=%s reason=%s",
                request.url.path,
                request.method,
                exc,
            )
            return JSONResponse(status_code=401, content={"detail": "authentication required"})
        return await call_next(request)


# Console (Vite) runs on a different origin than the API, so the browser
# requires CORS. Origins are configurable (R5); the default covers the local
# console on both loopback spellings. Never wildcard with credentials.
DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"


def _maintenance_tasks(app: FastAPI, transport: RealtimeTransport) -> list[ScheduledTask]:
    """Heartbeat tasks: approval timeout sweep (G2) + realtime buffer flush (G4).

    The sweep takes ``now_iso`` as a captured input (I4) and only appends TIMEOUT
    events (never auto-approves, I6). The flush is registered only when the transport
    exposes one (the degraded-bus buffer); it drains an already-persisted copy (I1).
    """

    def sweep(now_iso: str) -> int:
        return len(app.state.gateway.sweep_timeouts(now_iso=now_iso))

    tasks = [ScheduledTask(name="approval-timeout-sweep", run=sweep)]

    flush = getattr(transport, "flush", None)
    if callable(flush):

        def flush_buffer(now_iso: str) -> int:
            return int(flush())

        tasks.append(ScheduledTask(name="realtime-buffer-flush", run=flush_buffer))
    return tasks


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Run the maintenance heartbeat and stop lab subprocesses on shutdown."""
    app.state.scheduler.start()
    yield
    await app.state.scheduler.stop()
    app.state.server_manager.shutdown()
    app.state.realtime_transport.close()


class RestartSafeIdGenerator:
    """Deterministic event ids that stay unique across process restarts (I4).

    The platform SequenceIdGenerator restarts its counter at every process
    start, which would collide with event ids already persisted in the SQLite
    store. Instead of touching platform code, this generator derives a base
    offset at startup that is STRICTLY ABOVE every id already in the log:

        base = max( (existing_event_count + 1) * 1_000_000,
                    highest persisted EV-scheme id )

    The count-based term keeps the historical first id on a fresh store; the
    max-id term makes the base collision-proof regardless of how the log grew
    (variable per-process append counts across many restarts no longer realign
    onto an already-minted id -- a real failure mode once the gateway mints many
    ids per run, e.g. a governed campaign). Since the store is append-only (I1),
    every id minted after a restart lands strictly above all persisted ids. No
    clock, no randomness: the same store state always yields the same sequence.
    """

    _ID_RE = re.compile(r"EV(\d{24})\Z")

    def __init__(self, event_store: EventStore) -> None:
        events = event_store.read_from()
        count_base = (len(events) + 1) * 1_000_000
        highest = 0
        for event in events:
            match = self._ID_RE.match(event.event_id)
            if match is not None:
                highest = max(highest, int(match.group(1)))
        self._base = max(count_base, highest)
        self._n = 0

    def next_id(self) -> str:
        self._n += 1
        return f"EV{self._base + self._n:024d}"


def create_app(
    *,
    config_store: ConfigStore | None = None,
    event_store: EventStore | None = None,
    policy_store: PolicyStore | None = None,
    proxy: ExternalSystemProxy | None = None,
    catalog: Catalog | None = None,
    campaign_store: CampaignStore | None = None,
    recette_campaign_catalog: RecetteCampaignCatalog | None = None,
    recording_store: RecordingStore | None = None,
    verdict_store: VerdictStore | None = None,
    secret_store: BackendSecretStore | None = None,
    realtime_transport: RealtimeTransport | None = None,
) -> FastAPI:
    app = FastAPI(title="inspect_ia_agents Recette API", version="0.1.0", lifespan=_lifespan)

    # Identity binding (I3). The key is the only thing that turns enforcement on:
    # set in production, unset in dev/test. Resolved from env (R8), never hardcoded.
    auth_key = os.environ.get("INSPECT_IA_AGENTS_JWT_SIGNING_KEY") or None
    app.state.auth_key = auth_key
    if auth_key is None:
        _auth_logger.warning(
            "AUTH DISABLED: INSPECT_IA_AGENTS_JWT_SIGNING_KEY is unset -- the API accepts "
            "unauthenticated requests (dev/test mode). Production MUST set this key."
        )

    # Middleware added FIRST is innermost; CORS is added LAST so it wraps auth and
    # still stamps CORS headers on a 401. Auth runs after CORS resolves the request.
    app.add_middleware(JWTAuthMiddleware)
    _cors_raw = os.environ.get("INSPECT_IA_AGENTS_CORS_ORIGINS", DEFAULT_CORS_ORIGINS)
    cors_origins = [origin.strip() for origin in _cors_raw.split(",") if origin.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    cfg_store = config_store or ConfigStore()
    app.state.config_store = cfg_store
    # Per-backend AI keys live in a gitignored secret store, never in the
    # versioned config (R8). Resolved at LLM call time, never logged.
    app.state.secret_store = secret_store if secret_store is not None else BackendSecretStore()
    app.state.run_manager = RunManager()
    app.state.server_manager = ServerManager()
    # Connectivity-probe factory; tests override it with a stub (no key/network).
    app.state.llm_factory = build_llm

    if event_store is not None:
        events: EventStore = event_store
    else:
        # Phase 1/2 switch via INSPECT_IA_AGENTS_EVENT_STORE (sqlite default, postgres opt-in).
        events = build_event_store_from_env()
    # Realtime fan-out (G4): decorate the store so every append is diffused to the
    # live console stream. The store stays the source of truth (I1); the transport
    # is derived. Default in-process (mono-host); INSPECT_IA_AGENTS_REALTIME=nats opt-in.
    transport = (
        realtime_transport
        if realtime_transport is not None
        else build_realtime_transport_from_env()
    )
    app.state.realtime_transport = transport
    events = PublishingEventStore(events, transport)
    policies = policy_store if policy_store is not None else PolicyStore()
    base_proxy: ExternalSystemProxy = proxy if proxy is not None else LabHttpProxy()
    # Debug tracing decorates the I5 path: every gateway side effect is recorded
    # in a bounded in-memory ring (jettable, I1) read back by GET /proxy/traces.
    # Parametrable via INSPECT_IA_AGENTS_PROXY_DEBUG (R5); off => the wrapped proxy is
    # called directly with zero recording overhead.
    trace_recorder = RingTraceRecorder()
    app.state.proxy_trace_recorder = trace_recorder
    proxy_debug_enabled = debug_enabled_from_env()
    app.state.proxy_debug_enabled = proxy_debug_enabled
    side_effect_proxy: ExternalSystemProxy = TracingProxy(
        base_proxy, trace_recorder, enabled=proxy_debug_enabled
    )
    # Wire overlay (OPTIONAL, off by default): the network-level view of the same
    # I5 side effects, fed by the mitmproxy Docker overlay via POST /proxy/wire.
    # The recorder always exists (so the endpoints work); the overlay is only
    # "enabled" when INSPECT_IA_AGENTS_WIRE_PROXY names a proxy URL (R5). OFF keeps
    # the deterministic recette untouched (I4): nothing routes through a proxy.
    app.state.wire_flow_recorder = WireFlowRecorder()
    app.state.wire_proxy_url = wire_proxy_url_from_env()
    # Runtime-selectable transport route (direct vs wire overlay), surfaced in
    # the network-debug consoles. Transport only -- never the decision path (I4).
    app.state.proxy_route_registry = registry_from_env()
    action_catalog = catalog if catalog is not None else load_catalog()

    # Policy bootstrap: ensure an active version exists so the gateway never
    # starts without a policy. An empty catalog yields a zero-rule baseline,
    # which is still fail-safe: the engine is deny-by-default.
    if policies.active_version_id() is None:
        if BASELINE_POLICY_VERSION in policies.list_versions():
            # Version already published but the active pointer is missing.
            policies.set_active(BASELINE_POLICY_VERSION)
        else:
            # publish() auto-activates when no active pointer exists.
            policies.publish(baseline_from_catalog(action_catalog, version=BASELINE_POLICY_VERSION))

    app.state.event_store = events
    app.state.policy_store = policies
    app.state.catalog = action_catalog
    app.state.campaign_store = campaign_store if campaign_store is not None else CampaignStore()
    app.state.recette_campaign_catalog = (
        recette_campaign_catalog
        if recette_campaign_catalog is not None
        else RecetteCampaignCatalog()
    )
    app.state.recording_store = recording_store if recording_store is not None else RecordingStore()
    app.state.verdict_store = verdict_store if verdict_store is not None else VerdictStore()
    app.state.kb_store = KnowledgeBaseStore()
    app.state.gateway = Gateway(
        catalog=action_catalog,
        policy_store=policies,
        event_store=events,
        proxy=side_effect_proxy,
        id_generator=RestartSafeIdGenerator(events),
        agent_resolver=AgentResolver(cfg_store.get_agent),
    )
    app.state.scheduler = build_scheduler_from_env(_maintenance_tasks(app, transport))

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(config_router.router)
    app.include_router(catalog_router.router)
    app.include_router(runs_router.router)
    app.include_router(actions_router.router)
    app.include_router(policies_router.router)
    app.include_router(approvals_router.router)
    app.include_router(audit_router.router)
    app.include_router(catalog_actions_router.router)
    app.include_router(campaigns_router.router)
    app.include_router(recette_campaigns_router.router)
    app.include_router(agent_actions_router.router)
    app.include_router(verdicts_router.router)
    app.include_router(proxy_router.router)
    app.include_router(rag_router.router)
    app.include_router(subjects_router.router)
    app.include_router(sim_router.router)
    app.include_router(events_router.router)
    app.include_router(probe_router.router)
    app.include_router(discovery_router.router)
    return app
