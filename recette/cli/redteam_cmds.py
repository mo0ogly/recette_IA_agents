"""Red-team CLI commands: recette, promote, live record."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..redteam_git import run_git_scenario
from ..redteam_recette import run_scenario
from ..redteam_scorecard import render as render_redteam
from ..redteam_scorecard import scorecard as redteam_scorecard
from ._paths import _REPO_ROOT


def _cmd_redteam() -> int:
    """Replay every committed red-team scenario, print the scorecard.

    Covers BOTH families in sorted order (deterministic, I4): MAF subjects
    (corpus/sim/*.scenario.json via run_scenario) and git agents
    (corpus/sim/*.git-scenario.json via run_git_scenario). Aggregates with
    redteam_scorecard and returns a non-zero exit code when any anomaly was
    missed (predicted verdict diverged from the expected verdict). This is the
    same set the console /sim Scorecard tab mirrors."""
    sim_dir = _REPO_ROOT / "corpus" / "sim"
    outcomes = []
    # *.scenario.json (MAF) and *.git-scenario.json (git) are disjoint globs: the
    # git suffix is "-scenario.json", so the MAF glob never matches a git file.
    for path in sorted(sim_dir.glob("*.scenario.json")):
        with path.open(encoding="utf-8") as fh:
            outcomes.append(run_scenario(json.load(fh)))
    for path in sorted(sim_dir.glob("*.git-scenario.json")):
        with path.open(encoding="utf-8") as fh:
            outcomes.append(run_git_scenario(json.load(fh)))
    card = redteam_scorecard(outcomes)
    print(render_redteam(card))
    return 1 if card["missed"] else 0


def _cmd_redteam_promote(scenario_id: str, out: str | None, overwrite: bool) -> int:
    """Promote a caught red-team anomaly into a negative corpus subject.

    Locates the scenario (MAF or git), replays it, and -- if the re-judged
    verdict is ``incorrect`` and a single-axis violation -- freezes the three
    documents under ``<out>/incorrect/<slug>/`` (``out`` defaults to the family's
    corpus root when omitted). Returns 0 on success; 2 on a
    ValueError (correct/true-negative scenario, unknown id, or a multi-axis run)
    or a FileExistsError (already promoted -- suggests --overwrite)."""
    from ..redteam_promote import promote_scenario

    try:
        result = promote_scenario(scenario_id, out_root=out, overwrite=overwrite)
    except FileExistsError as exc:
        print(f"{exc}\n(re-run with --overwrite to replace the existing subject)", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(f"promoted {result['slug']}: verdict={result['verdict']} ({result['violation_type']})")
    for path in result["created"]:
        print(f"  wrote {path}")
    return 0


def _cmd_redteam_record(args: argparse.Namespace) -> int:
    """Run a LIVE red-team attack against a target subject, freeze it to a scenario.

    A real LLM provider (key from .env, R18) drives both the attacker
    (RedTeamSimulator) and the target subject; the run is recorded and frozen via
    the Phase-2 recorder into corpus/sim/<id>.scenario.json -- a deterministic,
    replayable artifact. This live path is NOT a gate (it needs a real key)."""
    from ..api._dotenv import load_dotenv
    from ..llm import LlmBackend, build_llm
    from ..manifest import load_validated
    from ..redteam import RedTeamSimulator
    from ..redteam_record import PyritAttacker, record_scenario, write_scenario
    from ..simulate import UserTurns

    load_dotenv()  # R18: keys resolve from .env

    try:
        spec = load_validated("manifest", Path(args.spec))
    except (ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"invalid target spec: {exc}", file=sys.stderr)
        return 2

    try:
        subject: LlmBackend = build_llm(args.subject_provider, args.subject_model)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.cache is not None:
        from ..llm_cache import CachingLlm, LlmCache

        cache = LlmCache(args.cache)
        subject = CachingLlm(
            subject, cache=cache, namespace=f"{args.subject_provider}:{args.subject_model}"
        )

    attacker: UserTurns
    if args.attacker == "pyrit":
        # Optional PyRIT driver ([real] extra); pyrit is imported lazily inside the
        # attacker's __call__, never here, so the CLI loads without the dependency.
        attacker = PyritAttacker(
            objective=args.objective or args.name,
            provider=args.attacker_provider,
            model=args.attacker_model,
            max_turns=args.max_turns,
        )
    else:
        # The native RedTeamSimulator needs a real attacker backend; the seeded
        # PyritAttacker does not, so --attacker-model is only required here.
        if not args.attacker_model:
            print("--attacker-model is required for --attacker native", file=sys.stderr)
            return 2
        try:
            attacker_backend: LlmBackend = build_llm(args.attacker_provider, args.attacker_model)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        if args.cache is not None:
            from ..llm_cache import CachingLlm, LlmCache

            cache = LlmCache(args.cache)
            attacker_backend = CachingLlm(
                attacker_backend,
                cache=cache,
                namespace=f"{args.attacker_provider}:{args.attacker_model}",
            )
        attacker = RedTeamSimulator(attacker_backend, max_turns=args.max_turns)

    tags = {
        k: v for k, v in (("owasp", args.owasp), ("mitre", args.mitre), ("nist", args.nist)) if v
    }

    scenario = record_scenario(
        spec=spec,
        subject=subject,
        user_turns=attacker,
        scenario_id=args.scenario_id,
        name=args.name,
        strategy=args.strategy,
        tags=tags,
        max_user_turns=args.max_turns,
    )

    out = write_scenario(scenario, args.out, overwrite=args.overwrite)
    print(f"froze red-team scenario: {out}")
    print(f"expected: {scenario['expected']}")
    return 0
