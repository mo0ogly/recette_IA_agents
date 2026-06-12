# recette/api/__main__.py
"""Run the U1 API: python -m recette.api  (host/port via env, lab is the default)."""

from __future__ import annotations

import os

import uvicorn

from ._dotenv import load_dotenv
from .app import create_app


def main() -> None:
    # Load provider keys (R8) from a gitignored .env if present; explicit
    # environment exports take precedence (override=False). Names only, no values.
    applied = load_dotenv()
    if applied:
        print(f"loaded {len(applied)} var(s) from .env: {', '.join(sorted(applied))}")
    uvicorn.run(
        create_app(),
        host=os.environ.get("AGENTRAIL_API_HOST", "127.0.0.1"),
        port=int(os.environ.get("AGENTRAIL_API_PORT", "8090")),
    )


if __name__ == "__main__":
    main()
