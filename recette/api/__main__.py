# recette/api/__main__.py
"""Run the U1 API: python -m recette.api  (host/port via env, lab is the default)."""

from __future__ import annotations

import os

import uvicorn

from .app import create_app


def main() -> None:
    uvicorn.run(
        create_app(),
        host=os.environ.get("AGENTRAIL_API_HOST", "127.0.0.1"),
        port=int(os.environ.get("AGENTRAIL_API_PORT", "8090")),
    )


if __name__ == "__main__":
    main()
