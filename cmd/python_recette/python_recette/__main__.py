"""CLI entry point: ``python -m python_recette <path>``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import patterns, report, scan, scoring, tools


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python_recette",
        description="Static recette scorer for AgentRail Python code (blocs A-F + tool gate)",
    )
    parser.add_argument("path", nargs="?", default=".", help="file or directory to audit")
    parser.add_argument("--format", choices=("text", "json"), default="text", help="output format")
    parser.add_argument("--project-dir", default=None, help="dir to run tools from (default: nearest project)")
    parser.add_argument("--skip-tools", action="store_true", help="skip Bloc D (ruff/mypy/bandit/pip-audit)")
    parser.add_argument("--min-score", type=int, default=39, help="minimum /44 score for exit code 0")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the recette; return process exit code (0 = gate passed)."""
    args = _parse_args(argv)
    target = Path(args.path)
    if not target.exists():
        print(f"python_recette: path not found: {target}", file=sys.stderr)
        return 1

    files = scan.collect_py_files(target)
    project_dir = Path(args.project_dir) if args.project_dir else scan.nearest_project_dir(target)

    results = patterns.run_all(files, project_dir)
    results.extend(tools.skipped_bloc_d() if args.skip_tools else tools.run_all(target, project_dir))

    scored = scoring.score(results)

    if args.format == "json":
        print(report.render_json(target, results, scored))
    else:
        print(report.render_text(target, results, scored))

    return 0 if scored.passes(args.min_score) else 1


if __name__ == "__main__":
    raise SystemExit(main())
