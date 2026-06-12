"""Per-backend AI API key secret store (R8).

The console lets an operator set ONE API key PER ai_backend entry. R8 forbids
storing secrets in the versioned config/agentrail.config.json (the ConfigStore
rejects api_key/token/secret fields, and keeps rejecting them). So keys live
HERE instead: a SEPARATE, gitignored JSON file keyed by backend id.

Guarantees:
- The file (default data/backend_secrets.json) is gitignored: never committed.
- A key is never logged and never echoed back in plaintext by the API layer;
  this store only reads/writes it for resolution at LLM call time.
- This file is the ONLY place a per-backend key lives -- it is intentionally
  separate from the versioned config so a config commit never leaks a secret.

Resolution order at call time (handled by the callers, not here): the
per-backend secret from this store first, then the provider's env var fallback
(implemented inside the provider classes in recette.llm).

Storage is a plain JSON object {backend_id: api_key}. Writes are atomic
(temp file + os.replace). A missing file reads as empty; the file is created
lazily on the first write.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def default_backend_secrets_path() -> Path:
    env = os.environ.get("AGENTRAIL_BACKEND_SECRETS_PATH")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent.parent / "data" / "backend_secrets.json"


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


class BackendSecretStore:
    """JSON-backed, gitignored map of {backend_id: api_key} (R8)."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path is not None else default_backend_secrets_path()

    def _read(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        return {str(k): str(v) for k, v in data.items()}

    def set_secret(self, backend_id: str, api_key: str) -> None:
        """Store the key for a backend. Empty/whitespace keys are rejected."""
        if not api_key or not api_key.strip():
            raise ValueError("api_key must be a non-empty value")
        secrets = self._read()
        secrets[backend_id] = api_key
        _atomic_write(self.path, json.dumps(secrets, indent=2) + "\n")

    def get_secret(self, backend_id: str) -> str | None:
        return self._read().get(backend_id)

    def delete_secret(self, backend_id: str) -> None:
        """Remove the key for a backend. Idempotent: unknown id is a no-op."""
        secrets = self._read()
        if backend_id not in secrets:
            return
        del secrets[backend_id]
        _atomic_write(self.path, json.dumps(secrets, indent=2) + "\n")

    def is_configured(self, backend_id: str) -> bool:
        return backend_id in self._read()

    def configured_ids(self) -> set[str]:
        return set(self._read().keys())
