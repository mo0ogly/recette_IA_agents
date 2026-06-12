"""Minimal stdlib .env loader -- zero hard dependency (no python-dotenv).

Loads KEY=VALUE lines from a .env file into os.environ at API startup so the
operator can keep provider keys (R8) in a gitignored file instead of exporting
them by hand. Environment variables already set win over the file (so an inline
`GROQ_API_KEY=... python -m recette.api` still overrides .env).

Format: one KEY=VALUE per line, # comments and blank lines ignored, surrounding
quotes on the value stripped. No interpolation, no multiline -- intentionally
tiny. Secrets are never logged.
"""

from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    """Repo root = three parents up from this file (recette/api/_dotenv.py)."""
    return Path(__file__).resolve().parent.parent.parent


def parse_env(text: str) -> dict[str, str]:
    """Parse .env text into a dict. Malformed lines are skipped, not fatal."""
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        out[key] = value
    return out


def load_dotenv(path: Path | None = None, *, override: bool = False) -> list[str]:
    """Load .env into os.environ. Returns the names of the keys applied.

    Missing file is a no-op (returns []). By default, an existing environment
    variable is NOT overwritten (override=False) so explicit exports win.
    """
    env_path = path if path is not None else repo_root() / ".env"
    if not env_path.is_file():
        return []
    applied: list[str] = []
    for key, value in parse_env(env_path.read_text(encoding="utf-8")).items():
        if override or key not in os.environ:
            os.environ[key] = value
            applied.append(key)
    return applied
