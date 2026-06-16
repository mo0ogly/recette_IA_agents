"""Live proof (R14): a real Groq agent runs THROUGH the in-process hook.

Wraps the real Groq backend in ``CapturingLlm`` and drives the demo-gh-bot agent.
Prints each captured decision -- the intent (tool:resource) plus the REAL
operational metrics (tokens from the provider response, measured latency). This
is the live evidence that the hook surface captures a real run, complementary to
the eBPF wire surface (discoveryprobe). Non-deterministic (live model); the
deterministic regression lives in tests/test_capturing_llm.py.

Key resolves from .env (R18: GROQ_API_KEY).

Usage: python3 scripts/run_capture_live_groq.py [--model llama-3.3-70b-versatile]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from recette.api._dotenv import load_dotenv  # noqa: E402
from recette.capture.capturing_llm import CapturingLlm  # noqa: E402
from recette.capture.llm_trace import LlmCallTrace  # noqa: E402
from recette.capture.surface_bridge import recording_from_traces  # noqa: E402
from recette.lane_b import run_agent  # noqa: E402
from recette.llm import build_llm  # noqa: E402
from recette.surface.surfaces import ObservationSurface  # noqa: E402

DEFAULT_MODEL = "llama-3.3-70b-versatile"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--max-steps", type=int, default=8)
    args = parser.parse_args()

    load_dotenv()
    traces: list[LlmCallTrace] = []
    llm = CapturingLlm(
        build_llm("groq", args.model),
        agent_id="demo-gh-bot",
        model=args.model,
        sink=traces.append,
    )

    run_agent(
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

    if not traces:
        print("[live] no decision captured", file=sys.stderr)
        return 1

    print(f"[live] hook captured {len(traces)} LLM decision(s):")
    for t in traces:
        intent = t.intent if t.kind == "tool_call" else "(reflexion)"
        print(f"  #{t.seq} {intent:24} tokens={t.total_tokens:<5} latency={t.latency_ms}ms")
    rec = recording_from_traces("demo-gh-bot", traces)
    hook = rec.surfaces.get(ObservationSurface.HOOK_SDK, ())
    print(f"[live] hook_sdk surface sees: {list(hook)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
