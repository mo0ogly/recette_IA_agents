"""Shared filesystem anchors for the CLI command modules."""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_DISCOVERY_GT_SCHEMA = _REPO_ROOT / "corpus" / "schemas" / "discovery-ground-truth.schema.json"
