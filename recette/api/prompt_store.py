"""Overrides-only store for the assist prompt catalog (Copilote IA).

Defaults live in code (``recette.api.assist_prompts``); this store persists
ONLY the operator overrides, as a flat ``{"overrides": {prompt_id: value}}``
JSON file. The file is gitignored (operator preference, not corpus ground
truth) and written atomically (temp + os.replace), same pattern as
``ConfigStore._write`` / ``BackendSecretStore``.

``resolve(prompt_id, default)`` re-reads the file on every call, so a PUT from
the console hot-reloads the very next LLM call with no process restart.

Failure mode (fail-safe, R7): a missing or corrupt file reads as "no
overrides" -- the copilot falls back to the in-code defaults rather than
breaking the assist endpoints.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

# Upper bound for one override value once JSON-serialized. Keeps a pathological
# PUT from bloating the file or the prompts sent to a provider.
MAX_OVERRIDE_CHARS = 64_000


def default_prompt_overrides_path() -> Path:
    env = os.environ.get("INSPECT_IA_AGENTS_PROMPT_OVERRIDES_PATH")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent.parent / "data" / "assist_prompt_overrides.json"


class PromptStore:
    """JSON-backed, gitignored map of {prompt_id: override value}."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path is not None else default_prompt_overrides_path()
        self._lock = threading.RLock()

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            # Tolerant load: a corrupt overrides file must never take the
            # assist endpoints down; defaults still apply.
            return {}
        overrides = data.get("overrides") if isinstance(data, dict) else None
        return dict(overrides) if isinstance(overrides, dict) else {}

    def _write(self, overrides: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(
            json.dumps({"overrides": overrides}, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, self.path)

    def get_override(self, prompt_id: str) -> Any | None:
        return self._read().get(prompt_id)

    def resolve(self, prompt_id: str, default: Any) -> Any:
        """Override-or-default, re-read on every call (hot reload)."""
        override = self.get_override(prompt_id)
        return default if override is None else override

    def set_override(self, prompt_id: str, value: Any) -> None:
        """Persist one override. Size-capped; emptiness is the caller's check."""
        serialized = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        if len(serialized) > MAX_OVERRIDE_CHARS:
            raise ValueError(f"override exceeds {MAX_OVERRIDE_CHARS} characters")
        with self._lock:
            overrides = self._read()
            overrides[prompt_id] = value
            self._write(overrides)

    def delete_override(self, prompt_id: str) -> None:
        """Reset one prompt to its default. Idempotent: unknown id is a no-op."""
        with self._lock:
            overrides = self._read()
            if prompt_id not in overrides:
                return
            del overrides[prompt_id]
            self._write(overrides)

    def overridden_ids(self) -> set[str]:
        return set(self._read().keys())
