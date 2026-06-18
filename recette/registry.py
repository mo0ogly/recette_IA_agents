"""Generated agent registry -- an aggregate registry row per corpus subject.

A read-only, GENERATED projection of the corpus subject manifests (never
hand-authored, like microsoft/discovery's auto-registry-on-merge): each subject
contributes a registry row with its identity, kind/family, version, target
systems, capability count, import provenance (``source.standard``) and the
optional registry metadata (publisher / compliance / party / tags). Pure
(``registry_row`` is a function of one manifest); the scanning + aggregation
lives in the API router.
"""

from __future__ import annotations


def registry_row(manifest: dict, family: str) -> dict:
    """One registry row from a subject manifest. Optional metadata fields are
    surfaced as None / [] when absent (never invented)."""
    metadata = manifest.get("metadata") or {}
    publisher = metadata.get("publisher") or {}
    source = manifest.get("source") or {}
    return {
        "agent_id": manifest.get("agent_id"),
        "name": manifest.get("name"),
        "kind": manifest.get("kind", "git_agent"),
        "family": family,
        "version": manifest.get("version"),
        "target_systems": manifest.get("target_systems", []),
        "capabilities": len(manifest.get("capability_scope", [])),
        "standard": source.get("standard"),
        "publisher": publisher.get("name"),
        "compliance": metadata.get("compliance", []),
        "party": metadata.get("party"),
        "tags": metadata.get("tags", []),
    }
