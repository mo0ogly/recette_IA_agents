"""Load the surface-detection corpus subjects (run view + ground-truth).

Each subject lives in corpus/surface/<slug>/ as run.json (proxy_traces +
wire_flows) and ground-truth.json (expected per-surface detection). Pure read,
sorted by slug for a stable order (I4).
"""

from __future__ import annotations

import json
from pathlib import Path

_CORPUS_ROOT = Path(__file__).resolve().parents[2] / "corpus" / "surface"


def load_surface_subjects(root: Path | None = None) -> list[dict]:
    base = root or _CORPUS_ROOT
    subjects: list[dict] = []
    for subject_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        run = json.loads((subject_dir / "run.json").read_text())
        ground_truth = json.loads((subject_dir / "ground-truth.json").read_text())
        subjects.append(
            {"agent_id": ground_truth["agent_id"], "run": run, "ground_truth": ground_truth}
        )
    return subjects
