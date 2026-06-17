"""GET /catalog/summary -- the declarative agent-catalog registry projection.

A discovery/registry source publishes a machine-readable index of agents (a
``version`` plus a list of entries declaring identity, purpose, and the tools
each agent is associated with). This route loads that committed registry and
projects it onto the INVARIANT discovery summary the recette judges -- total
entry count, distinct agent names, entries declaring at least one tool, and the
sorted, de-duplicated tag set -- plus a display list of agents in registry
order. It never exposes opaque values (R20: discovery ground-truth is
invariant-only, never an exact score). The projection mirrors the Rust catalog
crate's ``DiscoverySummary`` so both engines agree on the invariants.

Determinism (I4): the projection is a pure function of the registry JSON; tags
are sorted and de-duplicated, so the same registry yields a byte-stable summary.
``generated_at`` is operational metadata and never enters the projection.

Fail-safe: a missing, unreadable, or malformed registry yields an EMPTY catalog
(version "", empty summary, empty agents) with a logged warning -- never a 500.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess  # nosec B404
from pathlib import Path

from fastapi import APIRouter

router = APIRouter(prefix="/catalog", tags=["catalog"])

logger = logging.getLogger(__name__)

_REGISTRY_ENV = "INSPECT_IA_AGENTS_CATALOG_REGISTRY"
_DEFAULT_REGISTRY_REL = "corpus/catalog/agent-registry.json"
_REPO_ROOT = Path(__file__).resolve().parents[3]

_RUST_BIN_ENV = "INSPECT_IA_AGENTS_CATALOG_RUST_BIN"
_DEFAULT_RUST_BIN_REL = "discoveryprobe/target/release/discoveryprobe-catalog"
_RUST_ENGINE = "discoveryprobe-catalog (Rust)"


def _registry_path() -> Path:
    """The catalog registry path. Config first (R5): overridable via env, never
    a magic literal in the request path; defaults to the committed corpus
    registry resolved from the repo root."""
    raw = os.environ.get(_REGISTRY_ENV)
    if raw:
        return Path(raw)
    return _REPO_ROOT / _DEFAULT_REGISTRY_REL


def _empty_catalog() -> dict:
    """The fail-safe empty catalog (no registry / unreadable / malformed)."""
    return {
        "version": "",
        "summary": {"total": 0, "unique": 0, "with_tools": 0, "tags": []},
        "agents": [],
    }


def _project(registry: dict) -> dict:
    """Project a parsed registry onto the invariant summary + display agents.

    Pure: same registry -> byte-stable result (tags sorted + de-duplicated,
    agents in registry order). Mirrors the Rust ``DiscoverySummary``.
    """
    entries = registry.get("entries")
    if not isinstance(entries, list):
        entries = []

    names: set[str] = set()
    tags: set[str] = set()
    with_tools = 0
    agents: list[dict] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if isinstance(name, str):
            names.add(name)
        entry_tags = [t for t in entry.get("tags", []) if isinstance(t, str)]
        tags.update(entry_tags)
        associated = entry.get("associated_tools", [])
        foundry = entry.get("foundry_tools", [])
        associated = associated if isinstance(associated, list) else []
        foundry = foundry if isinstance(foundry, list) else []
        tool_count = len(associated) + len(foundry)
        if tool_count > 0:
            with_tools += 1
        publisher = entry.get("publisher_name")
        description = entry.get("description")
        agents.append(
            {
                "name": name if isinstance(name, str) else "",
                "version": entry.get("version") if isinstance(entry.get("version"), str) else "",
                "publisher_name": publisher if isinstance(publisher, str) else None,
                "description": description if isinstance(description, str) else None,
                "tags": entry_tags,
                "tool_count": tool_count,
            }
        )

    version = registry.get("version")
    return {
        "version": version if isinstance(version, str) else "",
        "summary": {
            "total": len(entries),
            "unique": len(names),
            "with_tools": with_tools,
            "tags": sorted(tags),
        },
        "agents": agents,
    }


def _load_catalog() -> dict:
    """Load + project the registry, fail-safe to an empty catalog on any error."""
    path = _registry_path()
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("catalog registry unreadable at %s: %s -> empty catalog", path, exc)
        return _empty_catalog()
    try:
        registry = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("catalog registry malformed at %s: %s -> empty catalog", path, exc)
        return _empty_catalog()
    if not isinstance(registry, dict):
        logger.warning("catalog registry not an object at %s -> empty catalog", path)
        return _empty_catalog()
    return _project(registry)


@router.get("/summary")
def summary() -> dict:
    """The invariant projection of the declarative agent-catalog registry.

    Returns ``{version, summary{total,unique,with_tools,tags[]}, agents[...]}``.
    Fail-safe: an absent/unreadable/malformed registry returns an empty catalog,
    never an error.
    """
    return _load_catalog()


def _rust_bin_path() -> Path:
    """The compiled Rust catalog engine binary. Config first (R5): env override,
    else the release build under the discoveryprobe workspace."""
    raw = os.environ.get(_RUST_BIN_ENV)
    if raw:
        return Path(raw)
    return _REPO_ROOT / _DEFAULT_RUST_BIN_REL


def _run_rust_summary() -> dict:
    """Invoke the Rust catalog engine on the registry and return its summary.

    The bridge that makes the native Rust discovery engine visible in the
    console: it runs the compiled ``discoveryprobe-catalog`` binary (no shell,
    fixed args -- the binary path and the registry path both come from config,
    never from request input) and parses its JSON summary. Fail-safe (R7): if the
    binary is absent, errors, times out, or returns non-JSON, returns
    ``available: false`` with a reason -- never a 500, never a fabricated result.
    """
    binary = _rust_bin_path()
    if not binary.is_file() or not os.access(binary, os.X_OK):
        return {
            "available": False,
            "engine": _RUST_ENGINE,
            "reason": f"binary not built at {binary} (cargo build --release)",
        }
    registry = _registry_path()
    try:
        # Fixed binary path + registry path from config, no shell, no request input.
        proc = subprocess.run(  # nosec B603
            [str(binary), str(registry)],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("rust catalog engine failed to run: %s", exc)
        return {"available": False, "engine": _RUST_ENGINE, "reason": str(exc)}
    if proc.returncode != 0:
        reason = proc.stderr.strip() or f"exit code {proc.returncode}"
        logger.warning("rust catalog engine exited %s: %s", proc.returncode, reason)
        return {"available": False, "engine": _RUST_ENGINE, "reason": reason}
    try:
        rust_summary = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        logger.warning("rust catalog engine returned non-JSON: %s", exc)
        return {"available": False, "engine": _RUST_ENGINE, "reason": "non-JSON output"}
    return {"available": True, "engine": _RUST_ENGINE, "summary": rust_summary}


@router.get("/rust-summary")
def rust_summary() -> dict:
    """Run the native Rust discovery engine on the registry and surface its result.

    Makes the otherwise CLI-only ``discoveryprobe-catalog`` engine visible in the
    console. Returns ``{available, engine, summary?, reason?, agreement?}`` where
    ``agreement`` is ``true`` iff the Rust invariant summary equals the Python
    projection (the cross-engine agreement the design guarantees). Fail-safe: an
    unbuilt or failing binary returns ``available: false``, never an error."""
    result = _run_rust_summary()
    if result.get("available"):
        python_summary = _load_catalog()["summary"]
        result["agreement"] = result["summary"] == python_summary
        result["python_summary"] = python_summary
    return result
