"""Report rendering: text (default) and JSON."""

from __future__ import annotations

import json
from pathlib import Path

from .model import CheckResult, Verdict
from .scoring import ScoreReport

_BLOCS = ("A", "B", "C", "D", "E", "F")


def render_json(target: Path, results: list[CheckResult], scored: ScoreReport) -> str:
    """Return the report as pretty JSON."""
    payload = {
        "target": str(target),
        "checks": [r.to_dict() for r in results],
        "scoring": scored.to_dict(),
    }
    return json.dumps(payload, indent=2)


def render_text(target: Path, results: list[CheckResult], scored: ScoreReport) -> str:
    """Return the report as human-readable text."""
    lines: list[str] = [f"RAPPORT PYTHON RECETTE - {target}", "=" * 42]
    for bloc in _BLOCS:
        in_bloc = [r for r in results if r.bloc == bloc]
        if not in_bloc:
            continue
        lines.append(f"\nBLOC {bloc}")
        lines.append("----")
        for r in in_bloc:
            verdict = {Verdict.PASS: "PASS", Verdict.FAIL: "FAIL", Verdict.NA: "N/A "}[r.verdict]
            note = f"  ({r.note})" if r.note else ""
            lines.append(f"{r.id:<4} {r.name:<34} : {verdict}{note}")
            for f in r.findings[:5]:
                lines.append(f"       - {f.file}:{f.line}  {f.excerpt}")
            if len(r.findings) > 5:
                lines.append(f"       ... {len(r.findings) - 5} more")

    lines.append("\n" + "=" * 42)
    for b in scored.blocs:
        if b.applicable == 0:
            lines.append(f"SCORE {b.bloc} : N/A (all manual/skipped)")
        else:
            lines.append(f"SCORE {b.bloc} : {b.score:.1f}/{b.max:.0f} ({b.passed}/{b.applicable} checks pass)")
    lines.append(
        f"SCORE GLOBAL : {scored.global_score:.1f}/{scored.global_max:.0f}  (normalized {scored.normalized_44:.1f}/44)"
    )
    lines.append(
        f"CRITIQUES en FAIL : {scored.critical_fails} | "
        f"Bloc E FAIL : {scored.e_fail} | Bloc F viole : {scored.f_violation}"
    )
    lines.append(f"VERDICT : {scored.verdict}")
    return "\n".join(lines)
