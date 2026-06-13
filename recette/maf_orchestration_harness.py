"""Harness for the multi-agent handoff orchestration corpus.

Discovers corpus/maf_orchestration/{correct,incorrect}/<slug>/ teams, validates
each (team + run against their schemas), runs the deterministic
judge_orchestration, and compares the verdict to the sibling ground-truth --
producing the same Scorecard the other recettes use. This extends the
credibility loop from single MAF subjects to MAF teams (HandoffBuilder meshes).
"""

from __future__ import annotations

from pathlib import Path

from .maf_orchestration import judge_orchestration, run_from_doc
from .manifest import load_validated
from .scorecard import AgentResult, Scorecard

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ORCHESTRATION_CORPUS = _REPO_ROOT / "corpus" / "maf_orchestration"


def discover_orchestration_dirs(root: Path = DEFAULT_ORCHESTRATION_CORPUS) -> list[Path]:
    """Return every team directory (containing team.json) under correct/ and incorrect/."""
    dirs: list[Path] = []
    for category in ("correct", "incorrect"):
        base = root / category
        if not base.is_dir():
            continue
        dirs.extend(d for d in sorted(base.iterdir()) if (d / "team.json").is_file())
    return dirs


def judge_dir(d: Path) -> AgentResult:
    """Validate, judge and score one orchestration directory against its ground-truth."""
    team = load_validated("maf_orchestration", d / "team.json")
    run_doc = load_validated("maf_orchestration_run", d / "run.json")
    ground_truth = load_validated("ground_truth", d / "ground-truth.json")

    ids = {team["agent_id"], run_doc["agent_id"], ground_truth["agent_id"]}
    if len(ids) != 1:
        raise ValueError(f"{d}: agent_id mismatch across files {ids}")

    run = run_from_doc(run_doc)
    result = judge_orchestration(team, run)
    # An orchestration is detectable as soon as it produced one observable step
    # (a handoff hop or a sequential/concurrent execution).
    detected = bool(run.hops or run.order)

    gt_id = ground_truth["expected_identification"]
    matches = {
        "detection": detected == ground_truth["expected_discovery"]["detectable"],
        "identity": result.identity_match == gt_id["identity"]["match"],
        "capabilities": result.capabilities_conform == gt_id["capabilities"]["conforms"],
        "policy": result.policy_compliant == gt_id["policy"]["compliant"],
        "behavior": result.behavior_expected == gt_id["behavior"]["expected"],
        "verdict": result.verdict == ground_truth["expected_verdict"],
    }
    return AgentResult(
        agent_id=team["agent_id"],
        category=ground_truth["category"],
        matches=matches,
        predicted_verdict=result.verdict,
        expected_verdict=ground_truth["expected_verdict"],
    )


def run_orchestration_recette(root: Path = DEFAULT_ORCHESTRATION_CORPUS) -> Scorecard:
    """Score every orchestration team in the corpus against its ground-truth."""
    scorecard = Scorecard()
    for d in discover_orchestration_dirs(root):
        scorecard.add(judge_dir(d))
    return scorecard
