"""Load the surface-detection corpus subjects (run view + ground-truth).

Each subject lives in corpus/surface/<slug>/ as run.json (proxy_traces +
wire_flows) and ground-truth.json (expected per-surface detection). Pure read,
sorted by slug for a stable order (I4).

Subjects whose slug starts with ``_`` are NOT scored by the green run
(``load_surface_subjects``): they are negatives (an agent seen on no surface)
used to exercise the RED gate, loaded separately via ``load_surface_negatives``.
"""

from __future__ import annotations

import json
from pathlib import Path

_CORPUS_ROOT = Path(__file__).resolve().parents[2] / "corpus" / "surface"
_NEGATIVE_DIR = "_negative"


def _load_dir(subject_dir: Path) -> dict:
    run = json.loads((subject_dir / "run.json").read_text())
    ground_truth = json.loads((subject_dir / "ground-truth.json").read_text())
    return {"agent_id": ground_truth["agent_id"], "run": run, "ground_truth": ground_truth}


def load_surface_subjects(root: Path | None = None) -> list[dict]:
    """Load the GREEN-scoring subjects (skips ``_``-prefixed dirs like _negative)."""
    base = root or _CORPUS_ROOT
    return [
        _load_dir(p) for p in sorted(base.iterdir()) if p.is_dir() and not p.name.startswith("_")
    ]


def load_surface_negatives(root: Path | None = None) -> list[dict]:
    """Load the negative subjects from corpus/surface/_negative/ (seen nowhere)."""
    base = (root or _CORPUS_ROOT) / _NEGATIVE_DIR
    if not base.is_dir():
        return []
    return [_load_dir(p) for p in sorted(base.iterdir()) if p.is_dir()]
