"""Strict gate scorer for the recette-full autonomous loop (the COMPLETE gate).

Consumes the deterministic sweep result (scripts/recette_full.py --json) and scores
it /100 across five dimensions, then applies a HARD, FAIL-CLOSED gate: the loop may
only COMPLETE when every deterministic subsystem is green, coverage is full, and the
total clears the target. Any deterministic FAIL blocks COMPLETE regardless of the
numeric total -- a red subsystem is never "averaged away".

Pure function of its inputs (I4 / R11): no clock, no random, no I/O into the score.
This is a judge path, so it stays deterministic and replayable.

Run:
  python3 scripts/recette_full.py --quick --json | python3 scripts/recette_score.py
  python3 scripts/recette_score.py --in sweep.json [--retex RETEX.md] [--target 90]
Exit code: 0 only when the gate PASSES; 1 otherwise (fail-closed).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Weighted dimensions (sum = 100). pass_rate carries the most weight AND backs the
# hard gate: a single deterministic failure cannot be diluted by the other axes.
_WEIGHTS = {
    "coverage": 25,  # did every expected subsystem actually run?
    "pass_rate": 35,  # are the deterministic subsystems green?
    "evidence": 15,  # does each verdict carry a command + headline?
    "determinism": 10,  # clean exits, no timeout / could-not-run
    "axes": 15,  # does the RETEX carry a non-empty improvement backlog?
}
# The deterministic subsystems the sweep MUST cover (the core checks).
_EXPECTED_CORE = 8


def _score_axes(retex_path: str | None) -> tuple[float, str]:
    """Improvement backlog present and filled? The RETEX's axes section must hold at
    least one concrete '[P..]' item that is not the empty placeholder."""
    if not retex_path:
        return 0.0, "no RETEX provided"
    text = Path(retex_path).read_text(encoding="utf-8")
    section = text.split("## Improvement axes", 1)
    if len(section) < 2:
        return 0.0, "RETEX has no improvement-axes section"
    body = section[1].split("##", 1)[0]
    items = [ln for ln in body.splitlines() if ln.strip().startswith("- [P")]
    concrete = [ln for ln in items if "<complete" not in ln and "<axis>" not in ln]
    if not concrete:
        return 0.0, "improvement axes empty (placeholder only)"
    return float(_WEIGHTS["axes"]), f"{len(concrete)} prioritized axis(es)"


def score(results: list[dict], retex_path: str | None, target: int) -> dict:
    """Score the sweep /100 and decide the fail-closed gate. Pure over its inputs."""
    n = len(results) or 1
    passed = [r for r in results if r.get("passed")]
    with_evidence = [r for r in results if str(r.get("headline", "")).strip()]
    clean = [
        r
        for r in results
        if r.get("exit_code") == 0 and "could not run" not in str(r.get("headline", ""))
    ]

    coverage = _WEIGHTS["coverage"] * min(len(results), _EXPECTED_CORE) / _EXPECTED_CORE
    pass_rate = _WEIGHTS["pass_rate"] * len(passed) / n
    evidence = _WEIGHTS["evidence"] * len(with_evidence) / n
    determinism = _WEIGHTS["determinism"] * len(clean) / n
    axes_pts, axes_note = _score_axes(retex_path)

    total = round(coverage + pass_rate + evidence + determinism + axes_pts, 1)

    # HARD GATE (fail-closed): every deterministic subsystem green + full coverage +
    # total clears the target. Any one failing blocks COMPLETE.
    all_green = len(passed) == n
    full_coverage = len(results) >= _EXPECTED_CORE
    reasons = []
    if not all_green:
        reasons.append(f"{n - len(passed)} deterministic subsystem(s) RED")
    if not full_coverage:
        reasons.append(f"coverage {len(results)}/{_EXPECTED_CORE} -- not all subsystems ran")
    if total < target:
        reasons.append(f"score {total} < target {target}")
    gate_pass = not reasons

    return {
        "breakdown": {
            "coverage": round(coverage, 1),
            "pass_rate": round(pass_rate, 1),
            "evidence": round(evidence, 1),
            "determinism": round(determinism, 1),
            "axes": round(axes_pts, 1),
        },
        "axes_note": axes_note,
        "total": total,
        "target": target,
        "gate_pass": gate_pass,
        "gate_reasons": reasons,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Strict fail-closed gate scorer for recette-full.")
    ap.add_argument("--in", dest="infile", default="", help="sweep JSON path (default: stdin)")
    ap.add_argument("--retex", default="", help="RETEX path to score the improvement-axes backlog")
    ap.add_argument(
        "--target", type=int, default=90, help="minimum total to pass the gate (default 90)"
    )
    args = ap.parse_args()

    raw = Path(args.infile).read_text(encoding="utf-8") if args.infile else sys.stdin.read()
    results = json.loads(raw)
    verdict = score(results, args.retex or None, args.target)

    b = verdict["breakdown"]
    print("=== recette-full gate score ===")
    for dim, pts in b.items():
        print(f"  {dim:12} {pts:5} / {_WEIGHTS[dim]}")
    print(f"  {'TOTAL':12} {verdict['total']:5} / 100   (target {verdict['target']})")
    print(f"  axes: {verdict['axes_note']}")
    if verdict["gate_pass"]:
        print("GATE: PASS -- COMPLETE allowed")
        return 0
    print("GATE: FAIL (fail-closed) -- REPLAN required:")
    for reason in verdict["gate_reasons"]:
        print(f"  - {reason}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
