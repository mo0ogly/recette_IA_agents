"""U1 app factory. Wires the routers onto a FastAPI instance.

The core recette package never imports this module — FastAPI stays an optional extra.
"""

from __future__ import annotations

from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="AgentRail Recette API", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
