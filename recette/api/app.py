"""U1 app factory. Wires the routers onto a FastAPI instance.

The core recette package never imports this module — FastAPI stays an optional extra.
"""

from __future__ import annotations

from fastapi import FastAPI

from .config_store import ConfigStore
from .routers import catalog as catalog_router
from .routers import config as config_router
from .routers import runs as runs_router
from .runs import RunManager


def create_app(*, config_store: ConfigStore | None = None) -> FastAPI:
    app = FastAPI(title="AgentRail Recette API", version="0.1.0")
    app.state.config_store = config_store or ConfigStore()
    app.state.run_manager = RunManager()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(config_router.router)
    app.include_router(catalog_router.router)
    app.include_router(runs_router.router)
    return app
