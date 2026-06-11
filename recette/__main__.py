"""CLI entrypoint: python -m recette validate | run."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .harness import DEFAULT_CORPUS, discover_agent_dirs, run_recette
from .manifest import load_ground_truth, load_manifest, load_scenario


def _cmd_validate(corpus_root: Path) -> int:
    """Validate every corpus artifact against its schema. Returns process exit code."""
    agent_dirs = discover_agent_dirs(corpus_root)
    if not agent_dirs:
        print(f"no agents found under {corpus_root}", file=sys.stderr)
        return 1
    errors = 0
    for d in agent_dirs:
        for kind, loader in (
            ("manifest", load_manifest),
            ("scenario", load_scenario),
            ("ground-truth", load_ground_truth),
        ):
            fname = "ground-truth.json" if kind == "ground-truth" else f"{kind}.json"
            try:
                loader(d / fname)
            except (ValueError, FileNotFoundError) as exc:
                errors += 1
                print(f"INVALID {d.name}/{fname}: {exc}", file=sys.stderr)
        # cross-file agent_id consistency
        try:
            ids = {
                load_manifest(d / "manifest.json")["agent_id"],
                load_scenario(d / "scenario.json")["agent_id"],
                load_ground_truth(d / "ground-truth.json")["agent_id"],
            }
            if len(ids) != 1:
                errors += 1
                print(f"INVALID {d.name}: agent_id mismatch across files {ids}", file=sys.stderr)
        except (ValueError, FileNotFoundError):
            pass  # already reported above
    if errors:
        print(f"\n{errors} validation error(s)", file=sys.stderr)
        return 1
    print(f"OK: {len(agent_dirs)} agents valid")
    return 0


def _cmd_run(corpus_root: Path) -> int:
    scorecard = run_recette(corpus_root)
    print(scorecard.render())
    return 0 if scorecard.all_passed else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="recette", description="AgentRail recette harness")
    parser.add_argument(
        "--corpus",
        type=Path,
        default=DEFAULT_CORPUS,
        help="path to corpus/agents (default: repo corpus)",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate", help="schema-validate all corpus artifacts")
    sub.add_parser("run", help="run the recette and print the scorecard")

    args = parser.parse_args(argv)
    if args.command == "validate":
        return _cmd_validate(args.corpus)
    if args.command == "run":
        return _cmd_run(args.corpus)
    parser.error(f"unknown command {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
