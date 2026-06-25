"""CLI handlers for the behavioral-analysis engine (`recette analyze`).

`wave` runs one tunable analysis pass over a frozen evidence bundle and prints a
report (human summary or `--json`); `replay` re-runs and asserts byte-equality
against a prior report -- the reproducibility proof a researcher cites. Pure: the
engine has no clock/random, so the CLI is a thin shell over `behavior.engine`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from ..behavior import AnalysisProfile, EvidenceBundle
from ..behavior.engine import replay, run_wave


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


def _cmd_analyze_wave(evidence: str, profile: str | None, threat: str | None, as_json: bool) -> int:
    try:
        bundle = EvidenceBundle.load(evidence)
        prof = _load_profile(profile, threat)
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
