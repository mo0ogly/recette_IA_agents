"""Live: a real Groq LLM drives every handoff/group_chat orchestration team in the
corpus; each run is recorded, replayed deterministically, and judged.

This is the end-to-end demonstration that a dynamic, non-deterministic LLM run
plugs into the deterministic agent-recette: the live model routes the team
(handoff_to_<target> / speak_<participant> tools and the agents' own tools), the
run is captured into an OrchestrationRecording (persistent), replayed via a
ReplayLlm (reproduces the exact same run -- I4), and scored on the four
dimensions by the same judge the offline corpus uses. With --freeze, a recording
is written back into the corpus as a new subject.

Only handoff and group_chat teams are LLM-driven (the model chooses the route);
sequential/concurrent topologies are structural and need no model, so they are
skipped here (they are covered by the offline corpus and tests/test_orchestrate).

Key: GROQ_API_KEY in the environment (R8, never hardcoded).

Usage:
  python3 scripts/run_orchestration_live_groq.py [--model llama-3.3-70b-versatile]
  python3 scripts/run_orchestration_live_groq.py --freeze-dir /tmp/frozen
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from recette.api._dotenv import load_dotenv  # noqa: E402
from recette.llm import build_llm  # noqa: E402
from recette.maf_orchestration_harness import discover_orchestration_dirs  # noqa: E402
from recette.manifest import load_validated  # noqa: E402
from recette.orchestrate import freeze_to_corpus, record, replay  # noqa: E402

_LLM_DRIVEN = ("handoff", "group_chat")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="run_orchestration_live_groq")
    parser.add_argument("--model", default="llama-3.3-70b-versatile")
    parser.add_argument("--max-steps", type=int, default=24)
    parser.add_argument(
        "--freeze-dir",
        default=None,
        help="if set, freeze each recording as a corpus subject under this dir",
    )
    args = parser.parse_args(argv)

    load_dotenv()  # R18: resolve GROQ_API_KEY from the gitignored .env if not already set
    try:
        llm = build_llm("groq", args.model)  # key from env (R8)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    teams = []
    for d in discover_orchestration_dirs():
        team = load_validated("maf_orchestration", d / "team.json")
        if team.get("style", "handoff") in _LLM_DRIVEN:
            teams.append(team)

    if not teams:
        print("no handoff/group_chat teams found", file=sys.stderr)
        return 1

    failures = 0
    for team in teams:
        rec = record(team, llm, provider="groq", model=args.model, max_steps=args.max_steps)
        try:
            _, result = replay(rec)
        except ValueError as exc:
            print(f"FAIL {team['agent_id']}: replay diverged ({exc})")
            failures += 1
            continue
        print(
            f"{team['agent_id']:42} style={team.get('style', 'handoff'):11} "
            f"decisions={len(rec.decisions):2} verdict={result.verdict}"
        )
        if args.freeze_dir:
            slug = f"live-{team['agent_id']}"
            category = "correct" if result.verdict == "correct" else "incorrect"
            vtype = None if category == "correct" else "behavior_anomaly"
            out = freeze_to_corpus(
                rec, args.freeze_dir, slug=slug, category=category, violation_type=vtype
            )
            print(f"    frozen -> {out}")

    print(f"\n{len(teams)} LLM-driven teams, {failures} replay divergence(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
