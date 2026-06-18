"""Corpus + report CLI commands: validate, run, maf, benchmark, report, import-maf."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema

from ..discovery_harness import SURFACE_CORPUS, SURFACE_ORDER, discover_repo_dirs
from ..harness import discover_agent_dirs, run_recette
from ..manifest import load_ground_truth, load_manifest, load_scenario
from ._paths import _DISCOVERY_GT_SCHEMA


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
    # Validate the standard-aligned (MAF) subject corpus.
    maf_errors, maf_count = _validate_maf_corpus()
    errors += maf_errors
    # Validate the multi-agent handoff orchestration corpus.
    orch_errors, orch_count = _validate_orchestration_corpus()
    errors += orch_errors

    if errors:
        print(f"\n{errors} validation error(s)", file=sys.stderr)
        return 1
    print(
        f"OK: {len(agent_dirs)} agents valid, {repo_count} discovery repos valid, "
        f"{maf_count} MAF subjects valid, {orch_count} orchestration teams valid"
    )
    return 0


def _validate_repo_corpus() -> tuple[int, int]:
    """Schema-validate discovery-ground-truth.json across every surface. Returns (errors, count)."""
    schema = json.loads(_DISCOVERY_GT_SCHEMA.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    errors = 0
    count = 0
    for surface in SURFACE_ORDER:
        for d in discover_repo_dirs(SURFACE_CORPUS[surface]):
            count += 1
            gt = json.loads((d / "discovery-ground-truth.json").read_text(encoding="utf-8"))
            for err in sorted(validator.iter_errors(gt), key=str):
                errors += 1
                print(
                    f"INVALID {surface}/{d.name}/discovery-ground-truth.json: {err.message}",
                    file=sys.stderr,
                )
            if gt.get("agent_repo") != d.name:
                errors += 1
                print(f"INVALID {surface}/{d.name}: agent_repo != dir name", file=sys.stderr)
    return errors, count


def _validate_maf_corpus() -> tuple[int, int]:
    """Schema-validate every MAF subject (spec/actions/ground-truth). Returns (errors, count)."""
    from ..maf_harness import discover_maf_dirs
    from ..manifest import load_validated

    errors = 0
    count = 0
    for d in discover_maf_dirs():
        count += 1
        for kind, fname in (
            ("manifest", "spec.json"),
            ("maf_actions", "actions.json"),
            ("ground_truth", "ground-truth.json"),
        ):
            try:
                doc = load_validated(kind, d / fname)
            except (ValueError, FileNotFoundError) as exc:
                errors += 1
                print(f"INVALID maf/{d.name}/{fname}: {exc}", file=sys.stderr)
                continue
            if doc.get("agent_id") != d.name:
                errors += 1
                print(f"INVALID maf/{d.name}/{fname}: agent_id != dir name", file=sys.stderr)
    return errors, count


def _validate_orchestration_corpus() -> tuple[int, int]:
    """Schema-validate every handoff team (team/run/ground-truth). Returns (errors, count)."""
    from ..maf_orchestration_harness import discover_orchestration_dirs
    from ..manifest import load_validated

    errors = 0
    count = 0
    for d in discover_orchestration_dirs():
        count += 1
        for kind, fname in (
            ("maf_orchestration", "team.json"),
            ("maf_orchestration_run", "run.json"),
            ("ground_truth", "ground-truth.json"),
        ):
            try:
                doc = load_validated(kind, d / fname)
            except (ValueError, FileNotFoundError) as exc:
                errors += 1
                print(f"INVALID orchestration/{d.name}/{fname}: {exc}", file=sys.stderr)
                continue
            if doc.get("agent_id") != d.name:
                errors += 1
                print(
                    f"INVALID orchestration/{d.name}/{fname}: agent_id != dir name",
                    file=sys.stderr,
                )
    return errors, count


def _cmd_run(corpus_root: Path) -> int:
    scorecard = run_recette(corpus_root)
    print(scorecard.render())
    return 0 if scorecard.all_passed else 1


def _cmd_maf() -> int:
    from ..maf_harness import run_maf_recette

    scorecard = run_maf_recette()
    print(scorecard.render())
    return 0 if scorecard.all_passed else 1


def _cmd_benchmark(as_json: bool) -> int:
    from ..benchmark import full_benchmark, render

    bench = full_benchmark()
    print(json.dumps(bench, indent=2) if as_json else render(bench))
    return 0


def _cmd_report(as_json: bool) -> int:
    from ..report import build_report

    report = build_report()
    if as_json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(report.render())
    return 0 if report.all_passed else 1


def _cmd_import_maf(spec_path: str, out: str | None) -> int:
    from ..import_maf import load_maf, maf_to_manifest
    from ..manifest import validate

    try:
        maf = load_maf(Path(spec_path))
        spec, gaps = maf_to_manifest(maf)
    except (ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"import-maf failed: {exc}", file=sys.stderr)
        return 2
    for gap in gaps:
        print(f"WARN unmapped MAF tool (no fabrication): {gap}", file=sys.stderr)
    errors = validate("manifest", spec)
    if errors:
        for err in errors:
            print(f"INVALID manifest: {err}", file=sys.stderr)
        return 2
    rendered = json.dumps(spec, indent=2)
    if out:
        Path(out).write_text(rendered + "\n", encoding="utf-8")
        print(f"wrote agent-spec draft: {out} ({len(spec['capability_scope'])} capabilities)")
    else:
        print(rendered)
    return 0
