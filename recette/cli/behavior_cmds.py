"""CLI handlers for the behavioral-analysis engine (`recette analyze`).

`wave` runs one tunable analysis pass over a frozen evidence bundle and prints a
report; `replay` asserts byte-equality against a prior report; the research
sub-commands (`metrics`, `sweep`, `ablate`, `export`) turn a wave into the
measurements a researcher publishes. Pure: the engine has no clock/random, so the
CLI is a thin shell over `behavior.engine` / `behavior.metrics`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from ..behavior import AnalysisProfile, EvidenceBundle
from ..behavior import metrics as M
from ..behavior.engine import replay, run_wave
from ..behavior.export import export_experiment


def _full_metrics(report, ground_truth: dict) -> dict:  # type: ignore[no-untyped-def]
    """The complete research metrics block for a report+ground-truth."""
    return {
        "confusion": M.confusion(report, ground_truth),
        "separation_auc": M.separation_auc(report, ground_truth),
        "roc": M.roc_curve(report, ground_truth),
        "standards_distribution": M.standards_distribution(report),
    }


def _load_profile(profile_path: str | None, threat: str | None) -> AnalysisProfile:
    if profile_path:
        data = json.loads(Path(profile_path).read_text(encoding="utf-8"))
    else:
        data = {}
    if threat:
        data["threat"] = threat
    return AnalysisProfile.from_dict(data)


def _render_summary(report: dict) -> str:
    lines = [
        f"wave: {report['profile_name']}  threat: {report['threat']}",
        f"experiment_id: {report['experiment_id']}",
        f"agents: {len(report['agents'])}",
    ]
    for a in report["agents"]:
        verdict = "coherent" if a["coherent"] else "DIVERGENT"
        fired = sorted({f["lens"] for f in a["findings"]})
        lines.append(
            f"  {a['agent_id']:<28} score={a['behavioral_score']:>3}  {verdict:<9} "
            f"lenses={fired or '-'}"
        )
        for f in a["findings"]:
            tag = "/".join(t for t in (f.get("owasp_asi"), f.get("mitre_atlas")) if t)
            lines.append(f"      [{f['severity']}] {f['log']}  ({tag})")
    return "\n".join(lines)


def resolve_discovery_cohort(profile: AnalysisProfile, mode: str | None) -> dict:
    """Fill profile.cohort['agents'] from a discovery scan; return the resolved
    cohort echo {mode, agents}. No-op echo when mode is falsy."""
    if not mode:
        return {"mode": None, "agents": profile.cohort.get("agents", ["*"])}
    from ..behavior.correlate import discovery_cohort
    from ..behavior.links import load_links

    agents = discovery_cohort(load_links(), mode)
    profile.cohort["agents"] = agents
    return {"mode": mode, "agents": agents}


def _cmd_analyze_wave(
    evidence: str,
    profile: str | None,
    threat: str | None,
    as_json: bool,
    cohort_discovery: str | None = None,
) -> int:
    try:
        bundle = EvidenceBundle.load(evidence)
        prof = _load_profile(profile, threat)
        echo = resolve_discovery_cohort(prof, cohort_discovery)
        if cohort_discovery:
            n = len(echo["agents"])
            print(f"cohort: {echo['mode']} -> {echo['agents']} ({n})")
        report = run_wave(bundle, prof).to_dict()
    except (OSError, ValueError) as exc:
        print(f"analyze: {exc}", file=sys.stderr)
        return 2
    if as_json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(_render_summary(report))
    return 0


def _cmd_analyze_replay(
    evidence: str, profile: str | None, threat: str | None, report_path: str
) -> int:
    try:
        bundle = EvidenceBundle.load(evidence)
        prof = _load_profile(profile, threat)
        prior = json.loads(Path(report_path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"analyze replay: {exc}", file=sys.stderr)
        return 2
    ok = replay(bundle, prof, prior)
    if ok:
        print(f"REPLAY OK -- byte-identical ({prior.get('experiment_id', '?')})")
        return 0
    print("REPLAY MISMATCH -- the report is not reproducible from this evidence+profile")
    return 1


def _load(evidence: str, profile: str | None, threat: str | None):  # type: ignore[no-untyped-def]
    bundle = EvidenceBundle.load(evidence)
    prof = _load_profile(profile, threat)
    return bundle, prof


def _render_confusion(cm: dict) -> str:
    return (
        f"  TP={cm['tp']} FP={cm['fp']} FN={cm['fn']} TN={cm['tn']}  "
        f"precision={cm['precision']} recall={cm['recall']} f1={cm['f1']}"
    )


def _cmd_analyze_metrics(
    evidence: str, profile: str | None, threat: str | None, as_json: bool
) -> int:
    """Ground-truth metrics for a wave: confusion, separation AUC, ROC, standards."""
    try:
        bundle, prof = _load(evidence, profile, threat)
    except (OSError, ValueError) as exc:
        print(f"analyze metrics: {exc}", file=sys.stderr)
        return 2
    if not bundle.ground_truth:
        print("analyze metrics: bundle has no ground_truth labels", file=sys.stderr)
        return 2
    report = run_wave(bundle, prof)
    metrics = _full_metrics(report, bundle.ground_truth)
    if as_json:
        print(json.dumps(metrics, indent=2, sort_keys=True))
        return 0
    print(f"metrics: profile={prof.name} threat={prof.threat}")
    print(_render_confusion(metrics["confusion"]))
    print(f"  separation_auc={metrics['separation_auc']}  roc_auc={metrics['roc']['auc']}")
    print(f"  standards={json.dumps(metrics['standards_distribution']['owasp_asi'])}")
    return 0


def _cmd_analyze_sweep(
    evidence: str, profile: str | None, threat: str | None, knob: str, values: str
) -> int:
    """Sweep a threshold knob across comma-separated values; print the confusion at
    each setting (the parametrable wave-variation -> operating-point curve)."""
    try:
        bundle, prof = _load(evidence, profile, threat)
        parsed = [_coerce(v) for v in values.split(",") if v != ""]
    except (OSError, ValueError) as exc:
        print(f"analyze sweep: {exc}", file=sys.stderr)
        return 2
    if not bundle.ground_truth:
        print("analyze sweep: bundle has no ground_truth labels", file=sys.stderr)
        return 2
    result = M.knob_sweep(bundle, prof, bundle.ground_truth, knob, parsed)
    print(f"sweep {knob}: ")
    for row in result["rows"]:
        print(
            f"  {knob}={row['value']!r}  TP={row['tp']} FP={row['fp']} "
            f"recall={row['recall']} precision={row['precision']}"
        )
    return 0


def _coerce(value: str):  # type: ignore[no-untyped-def]
    """Parse a sweep value: int if it looks like one, else the raw string."""
    try:
        return int(value)
    except ValueError:
        return value


def _cmd_analyze_ablate(evidence: str, profile: str | None, threat: str | None) -> int:
    """Per-lens ablation: drop each lens, measure the delta in detections."""
    try:
        bundle, prof = _load(evidence, profile, threat)
    except (OSError, ValueError) as exc:
        print(f"analyze ablate: {exc}", file=sys.stderr)
        return 2
    if not bundle.ground_truth:
        print("analyze ablate: bundle has no ground_truth labels", file=sys.stderr)
        return 2
    result = M.ablation(bundle, prof, bundle.ground_truth)
    print(f"ablation (base {_render_confusion(result['base']).strip()})")
    for c in result["lenses"]:
        print(
            f"  -{c['lens']:<12} delta_tp={c['delta_tp']:+d} "
            f"delta_fp={c['delta_fp']:+d} delta_recall={c['delta_recall']:+}"
        )
    return 0


def _cmd_analyze_export(evidence: str, profile: str | None, threat: str | None, out: str) -> int:
    """Write a self-contained, reproducible experiment package to ``out``."""
    try:
        bundle, prof = _load(evidence, profile, threat)
    except (OSError, ValueError) as exc:
        print(f"analyze export: {exc}", file=sys.stderr)
        return 2
    report = run_wave(bundle, prof)
    metrics = _full_metrics(report, bundle.ground_truth) if bundle.ground_truth else {}
    if bundle.ground_truth:
        metrics["ablation"] = M.ablation(bundle, prof, bundle.ground_truth)
    experiment_id = export_experiment(out, bundle, prof, report, metrics)
    print(f"experiment package -> {out}")
    print(f"experiment_id: {experiment_id}")
    return 0


def correlate_summary(rep: dict) -> str:
    """Human render of a correlation report. Pure string build."""
    q = rep["quadrants"]
    lines = [
        "=== Behavior <-> Discovery correlation ===",
        f"agree_clean={q['agree_clean']}  agree_dirty={q['agree_dirty']}  "
        f"static_blind={len(q['static_blind'])}  static_overflag={len(q['static_overflag'])}",
        "",
    ]
    for r in rep["rows"]:
        lines.append(
            f"  {r['agent_id']:<24} static_flagged={str(r['static_flagged']):<5} "
            f"runtime_dirty={str(r['runtime_dirty']):<5} score={r['behavioral_score']:>3}  "
            f"-> {r['quadrant']}"
        )
    if rep["unresolved"]:
        lines.append("")
        lines.append("UNRESOLVED (fail-loud):")
        for u in rep["unresolved"]:
            lines.append(f"  {u['agent_id']}: {u['reason']}")
    if rep["coverage_gaps"]:
        lines.append(
            "COVERAGE GAPS: " + ", ".join(g["discovery_subject"] for g in rep["coverage_gaps"])
        )
    return "\n".join(lines)


def _cmd_analyze_correlate(profile_path: str | None, threat: str | None, as_json: bool) -> int:
    """`recette analyze correlate` -- build discovery facts + a behavioral wave
    over each linked runtime, then classify into quadrants."""
    from ..behavior.correlate import build_discovery_facts, correlate
    from ..behavior.links import load_links

    links = load_links()
    discovery_facts = build_discovery_facts(links)
    # P1: behavior reports come from the wave the analyst already ran; here we
    # accept them from --profile's referenced reports dir, or empty (fail-loud).
    behavior_reports: dict = {}  # wired in Task 6 from the live wave; empty -> all evidence_missing
    thresholds = {"runtime_dirty": 50}
    rep = correlate(discovery_facts, behavior_reports, links, thresholds)
    if as_json:
        print(json.dumps(rep, sort_keys=True, indent=2))
    else:
        print(correlate_summary(rep))
    return 0
