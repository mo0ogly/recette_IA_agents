"""Experiment package -- a self-contained, citable artifact of one wave.

``export_experiment`` writes a folder holding everything needed to reproduce and
cite a wave: the frozen evidence, the profile, the report, and the research
metrics, plus a README pinning the ``experiment_id`` (evidence_hash | profile_hash
| tool_version). A reviewer re-runs ``recette analyze replay`` against the bundle
and the report and gets byte-equality -- reproducibility on disk.
"""

from __future__ import annotations

import json
from pathlib import Path

from .evidence import EvidenceBundle
from .profile import AnalysisProfile
from .report import AnalysisReport


def _write_json(path: Path, obj: object) -> None:
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def export_experiment(
    out_dir: str | Path,
    bundle: EvidenceBundle,
    profile: AnalysisProfile,
    report: AnalysisReport,
    metrics: dict,
) -> str:
    """Write the experiment package to ``out_dir`` and return the experiment_id."""
    folder = Path(out_dir)
    folder.mkdir(parents=True, exist_ok=True)
    bundle.save(folder / "evidence")
    _write_json(folder / "profile.json", profile.to_dict())
    _write_json(folder / "report.json", report.to_dict())
    _write_json(folder / "metrics.json", metrics)
    experiment_id = report.experiment_id()
    readme = (
        "# Behavioral-analysis experiment package\n\n"
        f"- experiment_id: `{experiment_id}`\n"
        f"- profile: `{profile.name}`  threat: `{profile.threat}`\n"
        f"- agents analyzed: {len(report.agents)}\n\n"
        "## Reproduce\n\n"
        "```\n"
        "python3 -m recette analyze replay "
        f"--evidence evidence --profile profile.json --report report.json\n"
        "```\n\n"
        "Byte-identical output (`REPLAY OK`) is the reproducibility guarantee (I4).\n"
        "Files: `evidence/bundle.json` (frozen input), `profile.json` (the wave),\n"
        "`report.json` (per-agent verdicts + findings), `metrics.json` (confusion,\n"
        "ROC, separation AUC, ablation, standards distribution).\n"
    )
    (folder / "README.md").write_text(readme, encoding="utf-8")
    return experiment_id
