"""Drive EVERY runtime agent (config/inspect_ia_agents.config.json) with SKYNET as the
live brain, against the mock lab (LabForge -- no side effects), and record each run.

SKYNET (gpt-oss-120b) is the engine of every agent here: one live LLM decides the
tool calls for all of them; the LabForge executes each target_system in-memory.
gpt-oss is a reasoning model that returns a final answer on a vague goal, so each
agent's goal is prefixed with a directive nudge toward tool use (the [P2] axis from
the recette-full RETEX, applied at the runner).

Free on SKYNET (internal), but SLOW (reasoning) -- expect a long wall-clock for 33
agents. Results (one line per agent) go to docs/tracking/recette/ (gitignored, R25).

Run: python3 scripts/run_agents_live_skynet.py [--max-steps 5] [--model openai/gpt-oss-120b]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))  # importable as `python3 scripts/X.py` from anywhere
_BASE = "https://api.skynet.cossi.internet"
_OUT = _ROOT / "docs" / "tracking" / "recette" / "agents_live_skynet.jsonl"

_NUDGE = (
    "Use your available tools to accomplish this now; call a tool on your first step, "
    "do not just describe the plan. Task: "
)


def _model_base_url(model: str) -> str:
    """Map a SKYNET model id to its per-model route. gpt-oss-120b -> /gpt-oss-120b/v1."""
    slug = model.split("/")[-1].replace("Qwen3.6", "qwen3.6")
    # The route slug matches the published model route; default to gpt-oss-120b.
    known = {"gpt-oss-120b": "gpt-oss-120b"}
    return f"{_BASE}/{known.get(slug, 'gpt-oss-120b')}/v1"


def run_one(agent: dict, llm: object, provider: str, model: str, max_steps: int) -> dict:
    """Drive one config agent with the live brain against LabForge. Never raises."""
    from recette.forge import LabForge
    from recette.lane_b import run_agent

    scope = [
        c if isinstance(c, str) else c.get("action") for c in agent.get("capability_scope", [])
    ]
    try:
        result = run_agent(
            agent_id=agent["id"],
            principal=agent.get("principal", agent["id"]),
            target_system=agent.get("target_system", ""),
            goal=_NUDGE + (agent.get("goal") or f"act as {agent['id']}"),
            capability_scope=[s for s in scope if s],
            llm=llm,  # type: ignore[arg-type]
            forge=LabForge(),
            provider=provider,
            model=model,
            max_steps=max_steps,
        )
        actions = [a for a in result.actions]
        in_scope = all(getattr(a, "action_type", None) in scope for a in actions)
        return {
            "agent_id": agent["id"],
            "target_system": agent.get("target_system", ""),
            "scope": scope,
            "actions": len(actions),
            "action_types": [getattr(a, "action_type", None) for a in actions],
            "in_scope": in_scope,
            "ok": True,
        }
    except Exception as exc:  # one agent failing must not abort the fleet
        return {"agent_id": agent["id"], "actions": 0, "ok": False, "error": str(exc)[:200]}


def main() -> int:
    ap = argparse.ArgumentParser(description="Drive every runtime agent with SKYNET live.")
    ap.add_argument("--max-steps", type=int, default=5)
    ap.add_argument("--model", default="openai/gpt-oss-120b")
    args = ap.parse_args()

    from recette.api._dotenv import load_dotenv

    load_dotenv()
    from recette.llm import build_llm

    base_url = _model_base_url(args.model)
    llm = build_llm("skynet", model=args.model, base_url=base_url)

    cfg = json.loads((_ROOT / "config" / "inspect_ia_agents.config.json").read_text())
    agents = cfg["agents"]
    _OUT.parent.mkdir(parents=True, exist_ok=True)

    results = []
    with _OUT.open("w", encoding="utf-8") as fh:
        for i, agent in enumerate(agents, 1):
            r = run_one(agent, llm, "skynet", args.model, args.max_steps)
            results.append(r)
            fh.write(json.dumps(r) + "\n")
            fh.flush()
            mark = "ok" if r["ok"] else "ERR"
            print(
                f"[{i}/{len(agents)}] {mark} {r['agent_id']:28} actions={r['actions']}", flush=True
            )

    acted = sum(1 for r in results if r["ok"] and r["actions"] > 0)
    errs = sum(1 for r in results if not r["ok"])
    out_scope = sum(1 for r in results if r.get("ok") and not r.get("in_scope", True))
    print(
        f"\nfleet done: {len(results)} agents | acted={acted} | "
        f"errors={errs} | out-of-scope={out_scope}\nresults: {_OUT}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
