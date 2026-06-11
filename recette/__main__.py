"""CLI entrypoint: python -m recette validate | run | discovery."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import jsonschema

from .discovery_harness import discover_repo_dirs, run_discovery_recette
from .harness import DEFAULT_CORPUS, discover_agent_dirs, run_recette
from .manifest import load_ground_truth, load_manifest, load_scenario

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DISCOVERY_GT_SCHEMA = _REPO_ROOT / "corpus" / "schemas" / "discovery-ground-truth.schema.json"


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
    # Validate the discovery repo corpus too.
    repo_errors, repo_count = _validate_repo_corpus()
    errors += repo_errors

    if errors:
        print(f"\n{errors} validation error(s)", file=sys.stderr)
        return 1
    print(f"OK: {len(agent_dirs)} agents valid, {repo_count} discovery repos valid")
    return 0


def _validate_repo_corpus() -> tuple[int, int]:
    """Schema-validate every discovery-ground-truth.json under corpus/repos. Returns (errors, count)."""
    repo_dirs = discover_repo_dirs()
    if not repo_dirs:
        return 0, 0
    schema = json.loads(_DISCOVERY_GT_SCHEMA.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    errors = 0
    for d in repo_dirs:
        gt = json.loads((d / "discovery-ground-truth.json").read_text(encoding="utf-8"))
        for err in sorted(validator.iter_errors(gt), key=str):
            errors += 1
            print(f"INVALID {d.name}/discovery-ground-truth.json: {err.message}", file=sys.stderr)
        if gt.get("agent_repo") != d.name:
            errors += 1
            print(f"INVALID {d.name}: agent_repo != dir name", file=sys.stderr)
    return errors, len(repo_dirs)


def _cmd_run(corpus_root: Path) -> int:
    scorecard = run_recette(corpus_root)
    print(scorecard.render())
    return 0 if scorecard.all_passed else 1


def _cmd_discovery(adapter_name: str) -> int:
    if adapter_name == "reference":
        adapter = None  # harness default = ReferenceSourceScanAdapter
    elif adapter_name == "http":
        from .http_adapter import HttpSourceScanAdapter

        adapter = HttpSourceScanAdapter()
    else:
        print(f"unknown adapter {adapter_name}", file=sys.stderr)
        return 2
    scorecard = run_discovery_recette(adapter)
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
    sub.add_parser("validate", help="schema-validate all corpus artifacts (agents + discovery repos)")
    sub.add_parser("run", help="run the identification recette and print the scorecard")
    disc = sub.add_parser("discovery", help="run the discovery recette over the repo corpus")
    disc.add_argument(
        "--adapter",
        choices=["reference", "http"],
        default="reference",
        help="reference = offline oracle (default); http = live Discovery :8081",
    )

    args = parser.parse_args(argv)
    if args.command == "validate":
        return _cmd_validate(args.corpus)
    if args.command == "run":
        return _cmd_run(args.corpus)
    if args.command == "discovery":
        return _cmd_discovery(args.adapter)
    parser.error(f"unknown command {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
