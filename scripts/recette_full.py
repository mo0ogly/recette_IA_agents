"""Deterministic recette sweep + RETEX skeleton emitter for the recette-full skill.

Runs the mock/deterministic recette of every subsystem (no LLM, no network, no
cost), aggregates a per-subsystem pass/fail, and writes a RETEX skeleton under
docs/tracking/recette/ (gitignored, R25) with the result table pre-filled. The
operator/agent then runs the scoped LIVE pass and completes the findings +
improvement axes.

This is ops tooling, NOT an agent/decision/judge path, so a wall-clock date for
the RETEX filename is fine (I4 governs the decision path, not a report stamp).
Pass --date to override for a reproducible filename.

Run: python3 scripts/recette_full.py [--quick] [--json] [--date YYYY-MM-DD]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

# (subsystem label, argv, core?) -- core checks always run; non-core skipped with --quick.
_CHECKS: list[tuple[str, list[str], bool]] = [
    ("schemas", ["python3", "-m", "recette", "validate"], True),
    ("identification", ["python3", "-m", "recette", "run"], True),
    ("discovery", ["python3", "-m", "recette", "discovery", "--adapter", "reference"], True),
    ("rust-probe/surface", ["python3", "-m", "recette", "surface"], True),
    ("scorecards/report", ["python3", "-m", "recette", "report", "--json"], True),
    ("red-team", ["python3", "-m", "recette", "redteam"], True),
    ("maf", ["python3", "-m", "recette", "maf"], True),
    ("rag", ["python3", "-m", "recette", "rag"], True),
    (
        "unittest (proxy/laneB/campaigns)",
        ["python3", "-m", "unittest", "discover", "-s", "tests"],
        False,
    ),
    ("gates (lint/type/security)", ["make", "gates"], False),
]


def _headline(out: str) -> str:
    """Last meaningful line of the command output -- the scorecard/summary line."""
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    return lines[-1][:200] if lines else ""


def run_check(label: str, argv: list[str]) -> dict[str, object]:
    """Run one deterministic check, capturing exit code + headline. Never raises."""
    try:
        proc = subprocess.run(argv, cwd=_ROOT, capture_output=True, text=True, timeout=1800)
        out = proc.stdout + proc.stderr
        return {
            "subsystem": label,
            "command": " ".join(argv),
            "exit_code": proc.returncode,
            "passed": proc.returncode == 0,
            "headline": _headline(out),
        }
    except subprocess.TimeoutExpired:
        return {
            "subsystem": label,
            "command": " ".join(argv),
            "exit_code": None,
            "passed": False,
            "headline": "TIMEOUT (>1800s)",
        }
    except OSError as exc:
        return {
            "subsystem": label,
            "command": " ".join(argv),
            "exit_code": None,
            "passed": False,
            "headline": f"could not run: {exc}",
        }


def sweep(quick: bool) -> list[dict[str, object]]:
    """Run the deterministic sweep (core checks; non-core skipped when quick)."""
    return [run_check(label, argv) for (label, argv, core) in _CHECKS if core or not quick]


def lane_b_manifest_from_corpus(corpus_manifest_path: str | Path) -> dict[str, object]:
    """Flatten a corpus identification manifest into the FLAT Lane B manifest that
    `recette agent run` expects (agent_id, principal, target_system singular, goal,
    capability_scope as action-id strings). The corpus shape uses target_systems
    (plural) + declared_identity.principal (nested) + capability_scope objects, so
    a direct hand-off raises KeyError('principal'); this is the correct bridge."""
    m = json.loads(Path(corpus_manifest_path).read_text(encoding="utf-8"))
    systems = m.get("target_systems") or [m.get("target_system")]
    scope = m.get("capability_scope", [])
    actions = [c["action"] if isinstance(c, dict) else c for c in scope]
    return {
        "agent_id": m["agent_id"],
        "principal": m["declared_identity"]["principal"],
        "target_system": systems[0],
        "goal": m.get("description") or m.get("name") or f"act as {m['agent_id']}",
        "capability_scope": actions,
    }


def render_retex(results: list[dict[str, object]], date: str) -> str:
    """Pre-fill the RETEX table from the sweep; leave findings + axes for the human."""
    rows = "\n".join(
        f"| {r['subsystem']} | {'PASS' if r['passed'] else 'FAIL'} | "
        f"`{r['command']}` -> exit {r['exit_code']} ; {r['headline']} |  |"
        for r in results
    )
    failed = [str(r["subsystem"]) for r in results if not r["passed"]]
    findings = "\n".join(f"- {f}" for f in failed) if failed else "- (deterministic pass all green)"
    return f"""# RETEX recette-full -- {date}

## Scope
- Deterministic pass: yes ({len(results)} subsystems)
- Live pass: none (run the scoped smoke separately and fill the rows below)
- SKIPPED: live agents / orchestration / campaigns / redteam-record (cost decision)

## Per-subsystem verdict
| Subsystem | Pass/Fail | Evidence (command + headline) | Notes |
|-----------|-----------|-------------------------------|-------|
{rows}

## Findings (anything not green, or surprising)
{findings}

## Improvement axes (the backlog -- prioritized)
- [P?] <complete after the live smoke: gaps, quick wins, refactors>

## Determinism / live notes
- Deterministic results above are byte-stable (I4).
- Live results (when added) are RECORDED, not replayed -- attach recording paths.
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Deterministic recette sweep + RETEX skeleton.")
    ap.add_argument("--quick", action="store_true", help="skip the slow unittest + gates checks")
    ap.add_argument("--json", action="store_true", help="print machine-readable result only")
    ap.add_argument("--date", default="", help="RETEX date (YYYY-MM-DD); default = today")
    args = ap.parse_args()

    results = sweep(args.quick)
    if args.json:
        print(json.dumps(results, indent=2))
        return 0 if all(r["passed"] for r in results) else 1

    date = args.date
    if not date:
        import datetime  # ops stamp only (not a decision path)

        date = datetime.date.today().isoformat()
    out_dir = _ROOT / "docs" / "tracking" / "recette"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"RETEX_recette-full_{date}.md"
    out_path.write_text(render_retex(results, date), encoding="utf-8")

    for r in results:
        mark = "PASS" if r["passed"] else "FAIL"
        print(f"[{mark}] {r['subsystem']:34} exit={r['exit_code']}  {r['headline']}")
    print(f"\nRETEX skeleton written: {out_path}")
    return 0 if all(r["passed"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
