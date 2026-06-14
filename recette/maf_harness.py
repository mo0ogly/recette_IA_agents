"""Harness for the standard-aligned (MAF) subject corpus.

Discovers corpus/maf_agents/{correct,incorrect}/<slug>/ subjects, validates each
(spec + actions against their schemas), runs the deterministic judge_maf, and
compares the verdict to the sibling ground-truth -- producing the same Scorecard
the git identification recette uses. This is the closed credibility loop: the
recette judges real MAF-shaped subjects on the four dimensions.
"""

from __future__ import annotations

from pathlib import Path

from .judge import judge_subject
from .maf_judge import MafAction
from .manifest import load_validated
from .scorecard import AgentResult, Scorecard

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MAF_CORPUS = _REPO_ROOT / "corpus" / "maf_agents"


def discover_maf_dirs(root: Path = DEFAULT_MAF_CORPUS) -> list[Path]:
    """Return every subject directory (containing spec.json) under correct/ and incorrect/."""
    dirs: list[Path] = []
    for category in ("correct", "incorrect"):
        base = root / category
        if not base.is_dir():
            continue
        for d in sorted(base.iterdir()):
            if (d / "spec.json").is_file():
                dirs.append(d)
    return dirs


def load_action_log(agent_id: str, actions_doc: dict) -> list[MafAction]:
    """Build the MafAction list from a validated actions document."""
    log: list[MafAction] = []
    for a in actions_doc["actions"]:
        log.append(
            MafAction(
                seq=a["seq"],
                agent_id=agent_id,
                provider=a["provider"],
                model=a["model"],
                action=a["action"],
                target=a["target"],
                tool_kind=a.get("tool_kind"),
                approved=bool(a.get("approved", False)),
            )
        )
    return log


def judge_dir(d: Path) -> AgentResult:
    """Validate, judge and score a single MAF subject directory against its ground-truth."""
    spec = load_validated("manifest", d / "spec.json")
    actions_doc = load_validated("maf_actions", d / "actions.json")
    ground_truth = load_validated("ground_truth", d / "ground-truth.json")

    ids = {spec["agent_id"], actions_doc["agent_id"], ground_truth["agent_id"]}
    if len(ids) != 1:
        raise ValueError(f"{d}: agent_id mismatch across files {ids}")

    action_log = load_action_log(spec["agent_id"], actions_doc)
    result = judge_subject(spec, action_log)
    # A subject is detectable as soon as it produced one observable action.
    detected = bool(action_log)

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
        agent_id=spec["agent_id"],
        category=ground_truth["category"],
        matches=matches,
        predicted_verdict=result.verdict,
        expected_verdict=ground_truth["expected_verdict"],
    )


def run_maf_recette(root: Path = DEFAULT_MAF_CORPUS) -> Scorecard:
    """Score every MAF subject in the corpus against its ground-truth."""
    scorecard = Scorecard()
    for d in discover_maf_dirs(root):
        scorecard.add(judge_dir(d))
    return scorecard
