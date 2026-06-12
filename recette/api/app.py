"""U1/A1 app factory. Wires the routers onto a FastAPI instance.

The core recette package never imports this module -- FastAPI stays an
optional extra. A1 adds the governed-execution wiring: event store (Audit
Plane, Phase 1 SQLite), policy store, lab proxy and the Gateway (I2).
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..platform.catalog import Catalog, load_catalog
from ..platform.eventstore import EventStore, SqliteEventStore
from ..platform.gateway import AgentResolver, Gateway
from ..platform.policy.model import baseline_from_catalog
from ..platform.policy.store import PolicyStore
from ..platform.proxy.lab_proxy import LabHttpProxy
from ..platform.proxy.protocol import ExternalSystemProxy
from .campaign_store import CampaignStore, RecordingStore
from .config_store import ConfigStore
from .routers import actions as actions_router
from .routers import agent_actions as agent_actions_router
from .routers import approvals as approvals_router
from .routers import audit as audit_router
from .routers import campaigns as campaigns_router
from .routers import catalog as catalog_router
from .routers import catalog_actions as catalog_actions_router
from .routers import config as config_router
from .routers import policies as policies_router
from .routers import runs as runs_router
from .runs import RunManager

DEFAULT_EVENT_STORE_PATH = "data/agentrail.events.db"
BASELINE_POLICY_VERSION = "v1"
# Console (Vite) runs on a different origin than the API, so the browser
# requires CORS. Origins are configurable (R5); the default covers the local
# console on both loopback spellings. Never wildcard with credentials.
DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"


class RestartSafeIdGenerator:
    """Deterministic event ids that stay unique across process restarts (I4).

    The platform SequenceIdGenerator restarts its counter at every process
    start, which would collide with event ids already persisted in the SQLite
    store. Instead of touching platform code, this generator derives a base
    offset from the current size of the append-only log at startup:

        base = (existing_event_count + 1) * 1_000_000

    Since the store is append-only (I1) and a single process never emits one
    million ids between restarts in this lab, every id minted after a restart
    lands strictly above all persisted ids. No clock, no randomness: the same
    store state always yields the same id sequence.
    """

    def __init__(self, event_store: EventStore) -> None:
        self._base = (len(event_store.read_from()) + 1) * 1_000_000
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
    recording_store: RecordingStore | None = None,
) -> FastAPI:
    app = FastAPI(title="AgentRail Recette API", version="0.1.0")

    cors_origins = [
        origin.strip()
        for origin in os.environ.get("AGENTRAIL_CORS_ORIGINS", DEFAULT_CORS_ORIGINS).split(",")
        if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    cfg_store = config_store or ConfigStore()
    app.state.config_store = cfg_store
    app.state.run_manager = RunManager()

    if event_store is not None:
        events: EventStore = event_store
    else:
        store_path = os.environ.get("AGENTRAIL_EVENT_STORE_PATH", DEFAULT_EVENT_STORE_PATH)
        events = SqliteEventStore(store_path)
    policies = policy_store if policy_store is not None else PolicyStore()
    side_effect_proxy: ExternalSystemProxy = proxy if proxy is not None else LabHttpProxy()
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
    app.state.recording_store = (
        recording_store if recording_store is not None else RecordingStore()
    )
    app.state.gateway = Gateway(
        catalog=action_catalog,
        policy_store=policies,
        event_store=events,
        proxy=side_effect_proxy,
        id_generator=RestartSafeIdGenerator(events),
        agent_resolver=AgentResolver(cfg_store.get_agent),
    )

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
    app.include_router(agent_actions_router.router)
    return app
