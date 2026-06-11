"""Discovery recette harness: runs the repo corpus through a SourceScanAdapter and scores it.

For each repo in corpus/repos/*:
  1. register the repo/ tree as a source, scan it, fetch the discovered risks
  2. scan a second time and compare -> determinism (invariant 7)
  3. compare risks to discovery-ground-truth.json on invariant properties
Then a cross-corpus check verifies relative risk ordering matches the ground-truth ranks.
"""

from __future__ import annotations

import json
from pathlib import Path

from .adapters import ReferenceSourceScanAdapter, SourceScanAdapter
from .discovery_scorecard import DiscoveryRepoResult, DiscoveryScorecard

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CORPUS = _REPO_ROOT / "corpus"
DEFAULT_REPO_CORPUS = _CORPUS / "repos"

# Scanner surface -> corpus sub-directory. github is corpus/repos for historical reasons.
SURFACE_CORPUS: dict[str, Path] = {
    "github": _CORPUS / "repos",
    "gitlab": _CORPUS / "gitlab",
    "temporal": _CORPUS / "temporal",
    "openapi": _CORPUS / "openapi",
    "mcp": _CORPUS / "manifests",
}
# Order surfaces are reported in when running "all".
SURFACE_ORDER: tuple[str, ...] = ("github", "gitlab", "temporal", "openapi", "mcp")


def discover_repo_dirs(corpus_root: Path | str = DEFAULT_REPO_CORPUS) -> list[Path]:
    corpus_root = Path(corpus_root)
    return sorted(p.parent for p in corpus_root.glob("*/discovery-ground-truth.json"))


def _risk_key(risks) -> list[tuple]:
    return sorted(
        (
            r.canonical_agent_id,
            r.action_pattern,
            r.target_system,
            json.dumps(r.estimated_risk, sort_keys=True),
            r.generated_policy or "",
        )
        for r in risks
    )


def _max_level(risks) -> int:
    return max((r.estimated_risk.get("level", 0) for r in risks), default=0)


def run_discovery_recette(
    adapter: SourceScanAdapter | None = None,
    corpus_root: Path | str = DEFAULT_REPO_CORPUS,
) -> DiscoveryScorecard:
    adapter = adapter or ReferenceSourceScanAdapter()
    scorecard = DiscoveryScorecard()
    levels: dict[str, int] = {}
    ranks: dict[str, int] = {}

    for repo_dir in discover_repo_dirs(corpus_root):
        gt = json.loads((repo_dir / "discovery-ground-truth.json").read_text(encoding="utf-8"))
        repo_tree = str(repo_dir / "repo")

        sid = adapter.register(repo_tree)
        adapter.await_run(adapter.scan(sid))
        risks = adapter.risks(sid)

        # Determinism (R7): a fresh source + scan must yield an identical risk set.
        sid2 = adapter.register(repo_tree)
        adapter.await_run(adapter.scan(sid2))
        risks2 = adapter.risks(sid2)
        deterministic = _risk_key(risks) == _risk_key(risks2)

        detected_actual = len(risks) > 0
        matches: dict[str, bool] = {
            "detection": detected_actual == gt["detected"],
            "determinism": deterministic,
        }
        detail: list[str] = []
        if not matches["detection"]:
            detail.append(f"detected={detected_actual} expected={gt['detected']}")
        if not deterministic:
            detail.append("non-deterministic risk set across scans")

        false_positive = (not gt["detected"]) and detected_actual
        false_negative = gt["detected"] and not detected_actual

        if gt["detected"]:
            distinct_ids = {r.canonical_agent_id for r in risks}
            matches["count"] = len(distinct_ids) == gt.get("agent_count", len(distinct_ids))
            if not matches["count"]:
                detail.append(f"agent_count={len(distinct_ids)} expected={gt.get('agent_count')}")

            got_actions = {r.action_pattern for r in risks}
            matches["actions"] = got_actions == set(gt.get("action_patterns", []))
            if not matches["actions"]:
                exp_actions = sorted(gt.get("action_patterns", []))
                detail.append(f"actions={sorted(got_actions)} expected={exp_actions}")

            matches["target"] = all(r.target_system == gt["target_system"] for r in risks)
            if not matches["target"]:
                detail.append("target_system mismatch")

            policy_present = any(bool(r.generated_policy) for r in risks)
            matches["policy"] = policy_present == gt.get("policy_generated", policy_present)
            if not matches["policy"]:
                detail.append(
                    f"policy_present={policy_present} expected={gt.get('policy_generated')}"
                )

            levels[repo_dir.name] = _max_level(risks)
            ranks[repo_dir.name] = gt.get("risk_rank", 0)

        scorecard.add(
            DiscoveryRepoResult(
                repo=repo_dir.name,
                detected_expected=gt["detected"],
                detected_actual=detected_actual,
                matches=matches,
                false_positive=false_positive,
                false_negative=false_negative,
                detail=detail,
            )
        )

    _check_ordering(scorecard, levels, ranks)
    return scorecard


def _check_ordering(
    scorecard: DiscoveryScorecard, levels: dict[str, int], ranks: dict[str, int]
) -> None:
    """Risk levels must be monotonic non-decreasing in the ground-truth rank (R5)."""
    ordered = sorted(ranks, key=lambda r: ranks[r])
    for a, b in zip(ordered, ordered[1:], strict=False):
        if ranks[a] < ranks[b] and levels.get(a, 0) > levels.get(b, 0):
            scorecard.ordering_ok = False
            scorecard.ordering_detail = (
                f"{a}(rank {ranks[a]}, level {levels.get(a)}) outranks "
                f"{b}(rank {ranks[b]}, level {levels.get(b)})"
            )
            return
