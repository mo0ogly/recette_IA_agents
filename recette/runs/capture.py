"""Thin helper: capture a surface (a set of named runs with artifacts) into
the eurodated run registry in one call.

Designed to be dropped into existing runners with minimal friction:
- The caller owns the eurodate strings (I4: no clock calls here).
- Capture errors are logged and never re-raised (fail-safe: a missing registry
  must never abort a live run).
- The existing flat-file writes and latest/ symlinks in the runners are kept
  intact for back-compat.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from .registry import RunRegistry

_log = logging.getLogger(__name__)


def capture_surface(
    *,
    category: str,
    group_id: str,
    eurodate: str,
    label: str = "",
    runs: dict[str, dict[str, Any]],
    registry: RunRegistry | None = None,
) -> RunRegistry | None:
    """Create a sealed group of runs in the registry.

    Parameters
    ----------
    category:
        Top-level category (e.g. "recette-full", "skynet", "agents").
    group_id:
        Unique id for this batch/launch (e.g. "2026-06-25-quick").
    eurodate:
        Operational timestamp string supplied by the caller (I4).
    label:
        Human-readable label for the group.
    runs:
        Mapping of run_id -> {kind: str, artifacts: {name: content}}.
    registry:
        Optional pre-built registry (tests inject this).  When None the
        env-default registry is used.

    Returns
    -------
    The :class:`RunRegistry` used, or None if capture failed (fail-safe).
    """
    try:
        reg = registry if registry is not None else RunRegistry()
        g = reg.new_group(
            category=category,
            group_id=group_id,
            eurodate=eurodate,
            label=label,
        )
        for run_id, run_spec in runs.items():
            kind: str = run_spec.get("kind", "unknown")
            r = reg.new_run(group=g, run_id=run_id, kind=kind, eurodate=eurodate)
            for name, content in (run_spec.get("artifacts") or {}).items():
                reg.write_artifact(r, name, content)
            reg.seal(r)
        _log.info(
            "capture_surface: sealed group %s/%s with %d run(s)",
            category,
            group_id,
            len(runs),
        )
        return reg
    except Exception as exc:  # noqa: BLE001
        _log.warning(
            "capture_surface failed for %s/%s (non-fatal): %s",
            category,
            group_id,
            exc,
        )
        return None


def update_latest_symlink(category: str, group_eurodate: str, group_id: str) -> None:
    """Update the latest/<category> symlink to the most recent group dir.

    This is back-compat only: existing scripts that read a flat latest/ path
    continue to work.  Errors are logged and swallowed (fail-safe).
    """
    try:
        reg = RunRegistry()
        latest_dir = reg._root / "latest"
        latest_dir.mkdir(parents=True, exist_ok=True)
        target = reg._root / category / f"{group_eurodate}_{group_id}"
        link = latest_dir / category
        if link.is_symlink() or link.exists():
            link.unlink()
        # Use a relative symlink so the tree is portable.
        try:
            rel = Path(os.path.relpath(target, latest_dir))
        except ValueError:
            rel = target  # absolute fallback on Windows or cross-drive
        link.symlink_to(rel)
        _log.debug("latest/%s -> %s", category, rel)
    except Exception as exc:  # noqa: BLE001
        _log.warning("update_latest_symlink failed for %s (non-fatal): %s", category, exc)
