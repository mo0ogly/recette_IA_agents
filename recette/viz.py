"""Mermaid visualization of an orchestration team and run (auto from the model).

Generates a Mermaid ``flowchart TD`` from a team definition (the DECLARED
structure, per style) and from a run (the ACTUAL routed path). Output conventions
mirror the real microsoft/agent-framework ``_workflows/_viz.py``: ``flowchart TD``
header, ``id["label"]`` nodes, ``a --> b`` edges, ``a -. label .-> b`` for
conditional/manager edges, ``((fan-in))`` for the concurrent join, and ids
sanitized (non-alphanumeric -> ``_``, prefixed ``n_`` when not starting with a
letter). Pure + deterministic (I4): a function of the team/run only.
"""

from __future__ import annotations

import re

from .maf_orchestration import OrchestrationRun


def _nid(name: str) -> str:
    """Sanitize an id like agent-framework _viz: non-alnum -> '_', 'n_' prefix if
    the result does not start with a letter."""
    s = re.sub(r"[^0-9a-zA-Z]", "_", name)
    return s if s[:1].isalpha() else f"n_{s}"


def team_mermaid(team: dict) -> str:
    """Render the team's DECLARED structure as a Mermaid flowchart, by style."""
    style = team.get("style", "handoff")
    participants = team["participants"]
    parts = [p["agent_id"] for p in participants]
    start = team.get("start_agent")
    lines = ["flowchart TD"]

    for p in parts:
        label = f"{p} (Start)" if (style == "handoff" and p == start) else p
        lines.append(f'    {_nid(p)}["{label}"];')

    if style == "handoff":
        for p in participants:
            for h in p.get("handoffs", []):
                lines.append(f'    {_nid(p["agent_id"])} --> {_nid(h["target"])};')
    elif style == "sequential":
        for a, b in zip(parts, parts[1:], strict=False):
            lines.append(f"    {_nid(a)} --> {_nid(b)};")
    elif style == "concurrent":
        lines.append('    dispatch["dispatch"];')
        lines.append("    agg((fan-in));")
        for p in parts:
            lines.append(f"    dispatch --> {_nid(p)};")
            lines.append(f"    {_nid(p)} --> agg;")
    else:  # group_chat | magentic -- manager-routed
        label = "next_speaker" if style == "magentic" else "speak"
        lines.append('    manager["manager"];')
        for p in parts:
            lines.append(f"    manager -. {label} .-> {_nid(p)};")

    return "\n".join(lines)


def run_mermaid(team: dict, run: OrchestrationRun) -> str:
    """Render the ACTUAL routed path of a run as a Mermaid flowchart."""
    lines = ["flowchart TD"]
    seen: set[str] = set()

    def _node(agent_id: str) -> None:
        if agent_id not in seen:
            seen.add(agent_id)
            lines.append(f'    {_nid(agent_id)}["{agent_id}"];')

    if run.hops:
        for hop in run.hops:
            _node(hop.source)
            _node(hop.target)
            lines.append(f"    {_nid(hop.source)} -->|{hop.seq}| {_nid(hop.target)};")
    else:
        for i, agent_id in enumerate(run.order):
            _node(agent_id)
            if i > 0:
                prev = run.order[i - 1]
                lines.append(f"    {_nid(prev)} -->|{i}| {_nid(agent_id)};")

    for call in run.calls:
        _node(call.agent_id)
        tool = call.tool_kind or call.target
        lines.append(f'    {_nid(call.agent_id)} -. {tool} .-> {_nid("tool_" + tool)}(["{tool}"]);')

    return "\n".join(lines)
