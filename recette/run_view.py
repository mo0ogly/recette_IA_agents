"""Step-through view of an orchestration run (DevUI-style trace viewer backend).

Turns a team + run into an ordered, render-ready timeline the console can step
through: one entry per structural step (handoff hop or sequential/concurrent/
group_chat/magentic turn) and one per tool call, plus the four-dimension verdict
and a Mermaid diagram of the routed path. Pure + deterministic (I4): a function
of (team, run) only. Our analog of the agent-framework DevUI trace view, built on
the recordings/corpus we already produce.
"""

from __future__ import annotations

from .maf_orchestration import OrchestrationRun, judge_orchestration
from .viz import run_mermaid


def build_run_view(team: dict, run: OrchestrationRun) -> dict:
    """Render a team+run as a step-through timeline + verdict + diagram."""
    result = judge_orchestration(team, run)
    style = team.get("style", "handoff")

    steps: list[dict] = []
    if run.hops:
        for hop in run.hops:
            steps.append(
                {
                    "index": len(steps),
                    "kind": "handoff",
                    "label": f"{hop.source} -> {hop.target}",
                    "from": hop.source,
                    "to": hop.target,
                }
            )
    else:
        for agent_id in run.order:
            steps.append(
                {
                    "index": len(steps),
                    "kind": "turn",
                    "label": agent_id,
                    "agent": agent_id,
                }
            )
    for call in run.calls:
        steps.append(
            {
                "index": len(steps),
                "kind": "tool",
                "label": f"{call.agent_id} · {call.tool_kind or call.target}",
                "agent": call.agent_id,
                "tool": call.tool_kind,
                "target": call.target,
                "approved": call.approved,
            }
        )

    return {
        "agent_id": team["agent_id"],
        "name": team.get("name", team["agent_id"]),
        "style": style,
        "verdict": result.verdict,
        "dimensions": {
            "identity": result.identity_match,
            "capabilities": result.capabilities_conform,
            "policy": result.policy_compliant,
            "behavior": result.behavior_expected,
        },
        "violations": [
            {"observed_action": v.observed_action, "kind": v.kind, "note": v.note}
            for v in result.capability_violations
        ],
        "steps": steps,
        "mermaid": run_mermaid(team, run),
    }
