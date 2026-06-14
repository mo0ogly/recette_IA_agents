"""Recette harness: runs the corpus through the tools and scores against ground-truth.

For each agent in the corpus:
  1. replay its scenario against a forge      -> action log
  2. run the discovery adapter                -> detected?
  3. run the identification adapter           -> 4 dimensions + verdict
  4. compare every output against ground-truth -> per-dimension match
The aggregated Scorecard reports detection rate, per-dimension accuracy, FP/FN.
"""

from __future__ import annotations

from pathlib import Path

from .adapters import (
    DiscoveryAdapter,
    IdentificationAdapter,
    ReferenceDiscoveryAdapter,
    ReferenceIdentificationAdapter,
)
from .agent import TestAgent
from .forge import LabForge
from .manifest import load_ground_truth
from .scorecard import AgentResult, Scorecard

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CORPUS = _REPO_ROOT / "corpus" / "agents"


def discover_agent_dirs(corpus_root: Path | str = DEFAULT_CORPUS) -> list[Path]:
    """Return every agent directory (one that holds a manifest.json), sorted."""
    corpus_root = Path(corpus_root)
    return sorted(p.parent for p in corpus_root.rglob("manifest.json"))


def run_agent(
    agent_dir: Path,
    *,
    discovery: DiscoveryAdapter,
    identification: IdentificationAdapter,
) -> AgentResult:
    agent = TestAgent.from_dir(agent_dir)
    ground_truth = load_ground_truth(agent_dir / "ground-truth.json")

    action_log = agent.run(LabForge())
    disc = discovery.discover(action_log)
    ident = identification.identify(manifest=agent.manifest, action_log=action_log)

    gt_disc = ground_truth["expected_discovery"]
    gt_ident = ground_truth["expected_identification"]

    matches = {
        "detection": disc.detected == gt_disc["detectable"],
        "identity": ident.identity_match == gt_ident["identity"]["match"],
        "capabilities": ident.capabilities_conform == gt_ident["capabilities"]["conforms"],
        "policy": ident.policy_compliant == gt_ident["policy"]["compliant"],
        "behavior": ident.behavior_expected == gt_ident["behavior"]["expected"],
        "verdict": ident.verdict == ground_truth["expected_verdict"],
    }

    return AgentResult(
        agent_id=agent.agent_id,
        category=ground_truth["category"],
        matches=matches,
        predicted_verdict=ident.verdict,
        expected_verdict=ground_truth["expected_verdict"],
    )


def run_recette(
    corpus_root: Path | str = DEFAULT_CORPUS,
    *,
    discovery: DiscoveryAdapter | None = None,
    identification: IdentificationAdapter | None = None,
) -> Scorecard:
    discovery = discovery or ReferenceDiscoveryAdapter()
    identification = identification or ReferenceIdentificationAdapter()
    scorecard = Scorecard()
    for agent_dir in discover_agent_dirs(corpus_root):
        scorecard.add(run_agent(agent_dir, discovery=discovery, identification=identification))
    return scorecard
