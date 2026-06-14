"""U1: read-only catalog of runnable subjects, built from the existing corpus helpers."""

from __future__ import annotations

from ..discovery_harness import SURFACE_CORPUS, SURFACE_ORDER, discover_repo_dirs
from ..harness import discover_agent_dirs
from ..manifest import load_ground_truth
from .config_store import ConfigStore


def build_catalog(store: ConfigStore) -> dict:
    identification = []
    for d in discover_agent_dirs():
        gt = load_ground_truth(d / "ground-truth.json")
        identification.append(
            {"agent_id": gt["agent_id"], "category": gt["category"], "dir": d.name}
        )
    discovery = {
        s: [d.name for d in discover_repo_dirs(SURFACE_CORPUS[s])]
        for s in SURFACE_ORDER
        if discover_repo_dirs(SURFACE_CORPUS[s])
    }
    return {
        "identification": identification,
        "discovery": discovery,
        "lane_b": store.read()["agents"],
    }
