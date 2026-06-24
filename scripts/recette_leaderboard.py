"""LLM governance leaderboard (A9): rank multiple LLMs by their governance score.

The benchmark's end goal -- the score is a PURE function of each LLM's captured
logs (I4), so two LLMs are comparable by construction. This aggregator reads one
or more per-LLM governance scorecards (each produced by
`recette_govscore.py --json` against that LLM's captured logs) and ranks them into
a comparable star table (LLM, stars, total, L1/L2/L3, engaged, resisted).

How to populate a row for a provider:
  1. run the live pass for that provider (the runners take --provider/--model/
     --base-url) into a per-provider log directory;
  2. `python3 scripts/recette_govscore.py --llm <provider/model> --dir <logs>
     --json > <provider>.scorecard.json`;
  3. `python3 scripts/recette_leaderboard.py skynet.scorecard.json groq.scorecard.json`.

Pure (I4): aggregation only, no clock, no random, stable ranking. With no
scorecard files passed, it scores the default SKYNET logs as the single row, so the
leaderboard always has at least the reference subject.

Run: python3 scripts/recette_leaderboard.py [scorecard.json ...] [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
_DIR = _ROOT / "docs" / "tracking" / "recette"


def rank(scorecards: list[dict]) -> list[dict]:
    """Rank scorecards by total desc (stable, name tiebreak). Pure."""
    rows = []
    for s in scorecards:
        lv = s.get("levels", {})
        m = s.get("metrics", {})
        rows.append(
            {
                "llm": s.get("llm", "?"),
                "stars": s.get("stars", 1),
                "total": s.get("total", 0.0),
                "L1": lv.get("L1_governance_hygiene", 0.0),
                "L2": lv.get("L2_behaviour_coherence", 0.0),
                "L3": lv.get("L3_adversarial_resistance", 0.0),
                "engaged": m.get("engaged", m.get("acted", 0)),
                "resisted": m.get("resisted", 0),
                "adversarial": m.get("adversarial", 0),
            }
        )
    return sorted(rows, key=lambda r: (-float(r["total"]), str(r["llm"])))


def to_markdown(rows: list[dict]) -> str:
    head = (
        "## LLM governance leaderboard\n\n"
        "| rank | LLM | stars | total | L1 | L2 | L3 | engaged | resisted/adv |\n"
        "|------|-----|-------|-------|----|----|----|---------|--------------|\n"
    )
    body = "\n".join(
        f"| {i} | {r['llm']} | {'*' * int(r['stars'])} | {r['total']} | {r['L1']} | "
        f"{r['L2']} | {r['L3']} | {r['engaged']} | {r['resisted']}/{r['adversarial']} |"
        for i, r in enumerate(rows, 1)
    )
    note = (
        "\n\nThe score is a pure function of each LLM's captured logs (I4), so the "
        "rows are comparable by construction. A row needs that LLM's live pass + its "
        "govscore JSON (see the module docstring)."
    )
    return head + body + note


def main() -> int:
    ap = argparse.ArgumentParser(description="Rank LLMs by governance score.")
    ap.add_argument("scorecards", nargs="*", help="per-LLM govscore JSON files")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.scorecards:
        cards = [json.loads(Path(p).read_text(encoding="utf-8")) for p in args.scorecards]
    else:
        # Default: score the reference SKYNET logs as the single row, so the
        # leaderboard always has at least the reference subject.
        from recette_govscore import score

        cards = [score(_DIR, "skynet/gpt-oss-120b")]

    rows = rank(cards)
    (_DIR / "leaderboard.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(json.dumps(rows, indent=2) if args.json else to_markdown(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
