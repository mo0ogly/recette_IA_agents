"""Sync the agent-catalog registry from a configurable source to the local file.

The catalog API (`GET /catalog/summary`) reads a LOCAL registry file, so its
request path stays deterministic and offline (I4 / R20). This module is the
explicit, operator-driven step that refreshes that file from a source -- the
only network touch, and it is recorded/replayable: the source URL is supplied by
configuration (env `INSPECT_IA_AGENTS_CATALOG_REGISTRY_URL`), never a hardcoded
location, and a `file://` source makes the whole sync exercisable without any
network (the test does exactly that).

Fail-safe: an unset source, an unsupported scheme, an unreachable source, or a
payload that is not a catalog registry raises :class:`CatalogSyncError` (logged)
-- it never writes a partial/garbage registry over the good local file.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

logger = logging.getLogger(__name__)

#: Env var holding the catalog source URL (config first, R5 -- no hardcoded source).
SOURCE_URL_ENV = "INSPECT_IA_AGENTS_CATALOG_REGISTRY_URL"
#: Env var holding the local registry destination (shared with the API router).
DEST_ENV = "INSPECT_IA_AGENTS_CATALOG_REGISTRY"
#: Default destination, relative to the repo root.
DEFAULT_DEST = "corpus/catalog/agent-registry.json"
#: Schemes the sync is allowed to read from.
_ALLOWED_SCHEMES = frozenset({"http", "https", "file"})


class CatalogSyncError(Exception):
    """A catalog sync could not complete (bad source, scheme, or payload)."""


def _fetch(url: str, timeout: float) -> str:
    """Read the raw source body, restricted to allow-listed schemes."""
    scheme = urlparse(url).scheme
    if scheme not in _ALLOWED_SCHEMES:
        raise CatalogSyncError(f"unsupported source scheme: {scheme!r}")
    try:
        # Scheme restricted to the allow-list above, so the urlopen audit is moot.
        with urlopen(url, timeout=timeout) as response:  # noqa: S310  # nosec B310
            return response.read().decode("utf-8")
    except OSError as exc:
        raise CatalogSyncError(f"source unreachable: {exc}") from exc


def sync_catalog(
    url: str | None = None,
    dest: Path | None = None,
    timeout: float = 10.0,
) -> Path:
    """Fetch the catalog registry from `url` and write it to `dest`.

    `url` defaults to ``$INSPECT_IA_AGENTS_CATALOG_REGISTRY_URL``; `dest` defaults
    to ``$INSPECT_IA_AGENTS_CATALOG_REGISTRY`` or :data:`DEFAULT_DEST`. The source
    MUST be a JSON object carrying an ``entries`` array (a catalog registry),
    otherwise the local file is left untouched and :class:`CatalogSyncError` is
    raised. Returns the path written.
    """
    source = url or os.environ.get(SOURCE_URL_ENV)
    if not source:
        raise CatalogSyncError(f"{SOURCE_URL_ENV} unset; provide a catalog source url")

    raw = _fetch(source, timeout)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CatalogSyncError(f"source is not valid JSON: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
        raise CatalogSyncError("source is not a catalog registry (object with 'entries')")

    target = dest or Path(os.environ.get(DEST_ENV) or DEFAULT_DEST)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    logger.info("catalog synced: %d entries -> %s", len(data["entries"]), target)
    return target


def main(argv: list[str] | None = None) -> int:
    """CLI: sync the catalog registry, printing the written path on success."""
    logging.basicConfig(level=logging.INFO)
    try:
        target = sync_catalog()
    except CatalogSyncError as exc:
        logger.error("catalog sync failed: %s", exc)
        return 1
    print(target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
