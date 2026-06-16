"""Live: a real Groq agent runs, then its SOURCE form is found by discovery.

This is the recording half of the Groq -> discovery loop (R20-compliant). A real
Groq model drives the `demo-gh-bot` github agent (read_repo -> open_pr) through
the Lane B decide->act loop against the in-memory lab. The run is RECORDED to a
replay fixture so the deterministic unittest
(`tests/test_discovery_groq_loop.py`) can replay it byte-stable (I4) without any
network or secret -- and, in the same test, assert that the agent's SOURCE form
(`corpus/repos/gh-pr-bot`) is detected by the discovery recette.

The two forms are the link (recette-corpus.md): the runtime agent ACTS
(read_repo + open_pr); the discovery subject is the publishable repo a scanner
sees. Discovery never observes the runtime -- it scans the source -- so the loop
is "real Groq agent behaves like a pr-bot" AND "discovery detects the pr-bot
repo", not "discovery watches the run".

Non-deterministic (live model); the recording it writes is what makes the
downstream recette deterministic. Key resolves from .env (R18: GROQ_API_KEY).

Usage: python3 scripts/run_discovery_loop_live_groq.py [--model llama-3.3-70b-versatile]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from recette.api._dotenv import load_dotenv  # noqa: E402
from recette.lane_b import run_agent  # noqa: E402
from recette.llm import build_llm  # noqa: E402

DEFAULT_MODEL = "llama-3.3-70b-versatile"
FIXTURE = (
    Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "discovery_loop_groq.replay.json"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--max-steps", type=int, default=8)
    parser.add_argument("--out", default=str(FIXTURE))
    args = parser.parse_args()

    load_dotenv()
    llm = build_llm("groq", args.model)

    # The demo-gh-bot runtime form: a github pr-bot, scope read_repo + open_pr.
    result = run_agent(
        agent_id="demo-gh-bot",
        principal="bot@acme",
        target_system="github",
        goal="Read the repository, then open a single pull request. Do both, once each.",
        capability_scope=["read_repo", "open_pr"],
        llm=llm,
        provider="groq",
        model=args.model,
        max_steps=args.max_steps,
        stop_on_repeat=True,
    )

    actions = [f"{a.action_type}:{a.resource}" for a in result.actions]
    print(f"[live] demo-gh-bot ran {len(result.actions)} action(s): {actions}")
    if not result.actions:
        print("[live] model proposed no tool call -- not recording an empty run", file=sys.stderr)
        return 1

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(result.recording.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"[live] recording written to {out} ({len(result.recording.decisions())} decision(s))")
    print("[live] replay it deterministically in tests/test_discovery_groq_loop.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
