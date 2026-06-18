"""Generated agent registry endpoint (GET /registry/agents).

Aggregates every corpus subject manifest (git agents + MAF subjects) into one
generated registry -- the auto-registry-on-merge concept: a derived aggregate,
never hand-authored. Read-only. Each row carries the subject's identity,
kind/family, version, target systems, capability count, import provenance and
the optional registry metadata (publisher/compliance/party/tags).
"""

from __future__ import annotations

import json

from fastapi import APIRouter

from ...harness import discover_agent_dirs
from ...maf_harness import discover_maf_dirs
from ...registry import registry_row

router = APIRouter(prefix="/registry", tags=["registry"])


def build_agent_registry() -> list[dict]:
    """Scan the subject dirs and build the generated registry (sorted by id)."""
    rows: list[dict] = []
    for directory in discover_agent_dirs():
        manifest_path = directory / "manifest.json"
        if manifest_path.exists():
            rows.append(registry_row(json.loads(manifest_path.read_text("utf-8")), "git"))
    for directory in discover_maf_dirs():
        spec_path = directory / "spec.json"
        if spec_path.exists():
            rows.append(registry_row(json.loads(spec_path.read_text("utf-8")), "maf"))
    return sorted(rows, key=lambda r: str(r["agent_id"]))


@router.get("/agents")
def agent_registry() -> dict:
    """The generated agent registry (one row per corpus subject)."""
    rows = build_agent_registry()
    return {"generated": True, "count": len(rows), "agents": rows}
