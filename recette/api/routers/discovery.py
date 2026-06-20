"""Discovery routes for the console dashboard.

``GET /discovery/check`` drives the reference source-scan adapter over the
published test repos (corpus/repos) and returns, per repo, whether discovery
DETECTED the agent's source form plus the invariant checks (detection,
determinism, ordering).

``GET /discovery/overview`` aggregates BOTH discovery sources -- the declarative
agent-catalog registry (catalog router) and the observability-signature table
(detect router) -- into one summary for a unified dashboard tile. It reuses the
existing load/project helpers of those routers (never duplicating their logic),
so the numbers always agree with ``/catalog/summary`` and ``/detect/signatures``.

Deterministic (I4), read-only. Fail-safe: empty/absent sources collapse to zeros,
never a 500.
"""

from __future__ import annotations

from fastapi import APIRouter

from ...discovery_harness import run_discovery_recette
from ...discovery_scorecard import DiscoveryScorecard
from ...surface.summary import surface_corpus_scorecard
from .catalog_registry import _load_catalog
from .detect import _load_signatures

router = APIRouter(prefix="/discovery", tags=["discovery"])


def _serialize(card: DiscoveryScorecard) -> dict:
    return {
        "all_passed": card.all_passed,
        "total": card.total,
        "passed": card.passed_count,
        "detection_rate": card.detection_rate,
        "false_positives": card.false_positives,
        "false_negatives": card.false_negatives,
        "ordering_ok": card.ordering_ok,
        "repos": [
            {
                "repo": r.repo,
                "detected": r.detected_actual,
                "expected": r.detected_expected,
                "passed": r.passed,
                "false_positive": r.false_positive,
                "false_negative": r.false_negative,
                "detail": r.detail,
            }
            for r in card.results
        ],
    }


@router.get("/check")
def check() -> dict:
    """Run the discovery recette over corpus/repos and return the detailed result."""
    return _serialize(run_discovery_recette())


def _overview() -> dict:
    """Aggregate the catalog registry + observability-signature sources.

    Pure projection over the two already-loaded sources: the catalog summary
    (``_load_catalog`` -> ``total``/``with_tools``/``tags``) and the signature
    table (``_load_signatures`` -> per-category and per-capability counts).
    ``by_category`` counts each tool's PRIMARY category; ``by_capability`` counts
    how many tools cover each capability (audit/replay surface here even though
    they are never a primary category). Keys are sorted so the same sources yield
    a byte-stable result (I4). Fail-safe: empty sources -> all zeros.
    """
    catalog = _load_catalog()
    summary = catalog.get("summary", {})
    tags = summary.get("tags", [])
    catalog_section = {
        "total": int(summary.get("total", 0)),
        "with_tools": int(summary.get("with_tools", 0)),
        "tags": len(tags) if isinstance(tags, list) else 0,
    }

    table = _load_signatures()
    by_category: dict[str, int] = {}
    by_capability: dict[str, int] = {}
    for entry in table:
        category = entry.get("category")
        if isinstance(category, str):
            by_category[category] = by_category.get(category, 0) + 1
        capabilities = entry.get("capabilities")
        if isinstance(capabilities, list):
            for capability in capabilities:
                if isinstance(capability, str):
                    by_capability[capability] = by_capability.get(capability, 0) + 1

    detect_section = {
        "tools": len(table),
        "by_category": {key: by_category[key] for key in sorted(by_category)},
        "by_capability": {key: by_capability[key] for key in sorted(by_capability)},
    }

    # The third discovery pillar: can the tool SEE the agent on each observation
    # surface (hook / eBPF-wire)? A subject seen nowhere is a ghost.
    card = surface_corpus_scorecard()
    surfaces_section = {
        "total_agents": card.total_agents,
        "detected_per_surface": {
            key: card.detected_per_surface[key] for key in sorted(card.detected_per_surface)
        },
        "ghosts": len(card.false_negatives),
        "ok": card.ok,
    }

    return {
        "catalog": catalog_section,
        "detect": detect_section,
        "surfaces": surfaces_section,
    }


@router.get("/overview")
def overview() -> dict:
    """Unified discovery overview for the console dashboard.

    Returns ``{catalog: {total, with_tools, tags}, detect: {tools, by_category,
    by_capability}, surfaces: {total_agents, detected_per_surface, ghosts, ok}}``
    aggregated from the catalog registry, the observability-signature table, and
    the surface corpus scorecard. Fail-safe: empty/absent sources yield zeros,
    never an error.
    """
    return _overview()
