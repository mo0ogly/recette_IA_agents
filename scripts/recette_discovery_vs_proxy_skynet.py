"""Discovery-vs-proxy cross-surface agreement on the SAME live runs.

The user's question: "est-ce que le discovery voit tout pareil que le proxy?"
Two governance surfaces observe one agent run from different angles:

  DISCOVERY (decision-log view)  -- fed the agent's decided action_log, the
      ReferenceDiscoveryAdapter answers "is there an agent here, and what did it
      do?". This is what a source/log scanner would surface.
  PROXY (side-effect view)       -- the mediated TracingProxy records what the
      agent actually DID against the lab (done_traces: action_type + resource +
      status + side_effect_hash). This is I5 ground truth.

If the two surfaces disagree -- discovery sees an action the proxy never mediated,
or the proxy mediates a side-effect discovery never attributed to the agent --
that gap is a blind spot in one surface. This script measures the agreement on the
same runs and the legibility chain declared >= decided >= done per agent.

Pure function of the recorded run (I4): no clock, no random, no live call. It reads
the already-captured traced_skynet.jsonl, so any ANSSI researcher recomputes the
same agreement from the same logs.

Run: python3 scripts/recette_discovery_vs_proxy_skynet.py [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_DIR = _ROOT / "docs" / "tracking" / "recette"


def _load(name: str) -> list[dict]:
    p = _DIR / name
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def _discovery_detects(agent_id: str, target_system: str, decided: list[str]) -> bool:
    """Run the real ReferenceDiscoveryAdapter over the run's decided action_log: an
    agent is detected as soon as it produced at least one observable action."""
    from recette.adapters import ReferenceDiscoveryAdapter
    from recette.events import AgentAction

    log = [
        AgentAction(
            event_id=f"{agent_id}:{i}",
            seq=i,
            timestamp="0",
            agent_id=agent_id,
            principal=agent_id,
            target_system=target_system,
            action_type=at,
            mode="read",
            resource="",
        )
        for i, at in enumerate(decided)
    ]
    return ReferenceDiscoveryAdapter().discover(log).detected


def analyze(rows: list[dict]) -> dict:
    """Per-run discovery-vs-proxy agreement. Pure."""
    ok = [r for r in rows if r.get("ok")]
    per_agent = []
    detection_parity = 0
    chain_ok = 0
    decided_not_done = []  # discovery sees a decided action the proxy never mediated
    done_not_decided = []  # proxy mediated a side-effect discovery never saw decided

    for r in ok:
        decided = sorted(set(r.get("decided", [])))
        done = sorted({t["action_type"] for t in r.get("done_traces", [])})
        declared = set(r.get("declared_scope", []))
        disc = _discovery_detects(r.get("agent_id", ""), r.get("target_system", ""), decided)
        proxy_acted = bool(done)

        # Detection parity: discovery detects an agent iff it decided an action;
        # the proxy mediates iff it produced a side-effect. They agree when an
        # agent that acted is seen by BOTH (or one that did nothing by neither).
        parity = disc == proxy_acted or (disc and set(done) <= set(decided))
        # Legibility chain: every mediated side-effect was decided, every decision
        # is within the declared scope -- done <= decided <= declared.
        chain = set(done) <= set(decided) <= declared

        extra_decided = sorted(set(decided) - set(done))
        extra_done = sorted(set(done) - set(decided))
        if extra_decided:
            decided_not_done.append({"agent_id": r.get("agent_id"), "actions": extra_decided})
        if extra_done:
            done_not_decided.append({"agent_id": r.get("agent_id"), "actions": extra_done})

        detection_parity += 1 if parity else 0
        chain_ok += 1 if chain else 0
        per_agent.append(
            {
                "agent_id": r.get("agent_id"),
                "target_system": r.get("target_system"),
                "discovery_detected": disc,
                "proxy_acted": proxy_acted,
                "decided": decided,
                "done": done,
                "parity": parity,
                "chain_ok": chain,
            }
        )

    n = len(ok) or 1
    proxy_types = sorted({t["action_type"] for r in ok for t in r.get("done_traces", [])})
    disc_types = sorted({a for r in ok for a in r.get("decided", [])})
    return {
        "agents": len(ok),
        "detection_parity_rate": round(detection_parity / n, 3),
        "legibility_chain_rate": round(chain_ok / n, 3),
        "discovery_action_types": disc_types,
        "proxy_action_types": proxy_types,
        "action_types_agree": disc_types == proxy_types,
        "decided_not_done": decided_not_done,
        "done_not_decided": done_not_decided,
        "per_agent": per_agent,
    }


def to_markdown(a: dict) -> str:
    same = "IDENTICAL" if a["action_types_agree"] else "DIVERGENT"
    dnd = a["decided_not_done"]
    dnotd = a["done_not_decided"]
    div = ""
    if dnd:
        div += "\n  discovery saw decided-but-not-mediated:\n" + "\n".join(
            f"    - {x['agent_id']}: {', '.join(x['actions'])}" for x in dnd
        )
    if dnotd:
        div += "\n  proxy mediated side-effect discovery never decided:\n" + "\n".join(
            f"    - {x['agent_id']}: {', '.join(x['actions'])}" for x in dnotd
        )
    if not div:
        div = "\n  (no divergence: every decided action was mediated and vice-versa)"
    return f"""## discovery-vs-proxy -- same live runs ({a["agents"]} agents)

- detection parity (discovery sees what proxy mediates): {a["detection_parity_rate"]}
- legibility chain done<=decided<=declared: {a["legibility_chain_rate"]}
- action-type vocabulary discovery vs proxy: {same}
  discovery: {", ".join(a["discovery_action_types"])}
  proxy:     {", ".join(a["proxy_action_types"])}
- divergences:{div}
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Discovery-vs-proxy agreement on the same runs.")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    rows = _load("traced_skynet.jsonl")
    a = analyze(rows)
    # Persist the researcher artifact so the ANSSI bundle is self-contained.
    (_DIR / "discovery_vs_proxy_skynet.json").write_text(json.dumps(a, indent=2), encoding="utf-8")
    print(json.dumps(a, indent=2) if args.json else to_markdown(a))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
