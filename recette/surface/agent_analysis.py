"""The discovery's JOB: per agent, compare PLANNED (declared) vs SAID (decided) vs
DONE (what the kernel/proxy saw), and SAY WHAT TO LOG.

This is the legibility-first three-way coherence (CLAUDE.md), computed at the
discovery/probe layer so the console can REPORT it:

  PLANNED (declared) -- the agent's `capability_scope` + the servers it is allowed
                        to reach (the registry).
  SAID (decided)     -- the action_types the agent decided (the action-log), when a
                        run is linked; the eBPF probe alone does not see semantics.
  DONE (seen)        -- the kernel surface: which servers it actually dialed, which
                        DNS it resolved, which child it spawned (the eBPF wire).

From the gaps it derives concrete LOGGING RECOMMENDATIONS (what an operator should
log/alert for this agent) and a short ANALYSIS. Pure (I4): no clock, no random,
stable order -- byte-stable on replay, so the console renders a deterministic report
and an ANSSI researcher recomputes the same one.
"""

from __future__ import annotations

# Severity tiers for a logging recommendation, worst first (stable order).
_SEVERITY_ORDER = {"alert": 0, "warn": 1, "info": 2}


def _rec(severity: str, what: str, why: str) -> dict:
    return {"severity": severity, "log": what, "why": why}


def analyze_agent(
    agent_id: str,
    *,
    declared_scope: list[str],
    declared_systems: list[str],
    wire_annotations: list[dict],
    decided_actions: list[str] | None = None,
) -> dict:
    """Three-way coherence + logging recommendations for ONE agent. Pure.

    `wire_annotations` is the per-token output of `netmap.annotate_token`
    (kind/name/undeclared/category). `decided_actions` is the action-log
    action_types when a run is linked (None when only the kernel surface is known).
    """
    seen_kinds = sorted({a.get("kind", "other") for a in wire_annotations})
    dialed = sorted(
        {str(a["name"]) for a in wire_annotations if a.get("kind") == "connect" and a.get("name")}
    )
    undeclared_egress = sorted(
        a["raw"][len("connect:") :]
        for a in wire_annotations
        if a.get("kind") == "connect" and a.get("undeclared")
    )
    undeclared_dns = sorted(
        a["raw"][len("dns:") :]
        for a in wire_annotations
        if a.get("kind") == "dns" and a.get("undeclared")
    )
    process_spawned = any(a.get("kind") in ("fork", "exec") for a in wire_annotations)
    sensitive_opens = sorted(
        path
        for a in wire_annotations
        if a.get("kind") == "open" and a.get("category") in ("etc", "other")
        for path in [a["raw"][len("open:") :]]
        if path and path != "<unknown>"
    )
    identified = bool(wire_annotations)

    # PLANNED vs DONE coherence at the network layer: every dialed server is a
    # declared target system. (SAID is folded in only when decided_actions given.)
    declared_set = set(declared_systems)
    out_of_plan_servers = sorted(s for s in dialed if s not in declared_set)
    said_out_of_scope = (
        sorted(a for a in (decided_actions or []) if a not in set(declared_scope))
        if decided_actions is not None
        else []
    )
    coherent = (
        not undeclared_egress
        and not undeclared_dns
        and not out_of_plan_servers
        and not said_out_of_scope
    )

    # --- Logging recommendations (the "say what to log" job) ---
    recs: list[dict] = []
    for host in undeclared_egress:
        recs.append(
            _rec(
                "alert",
                f"egress connect to UNDECLARED host {host}",
                "possible exfiltration -- not in the server registry",
            )
        )
    for name in undeclared_dns:
        recs.append(
            _rec(
                "alert",
                f"DNS query for UNDECLARED name {name}",
                "possible DNS exfil/tunneling -- outside declared fqdns",
            )
        )
    for srv in out_of_plan_servers:
        recs.append(
            _rec(
                "warn",
                f"connect to server {srv} OUTSIDE the declared target systems",
                "capability drift -- server not in the agent's plan",
            )
        )
    for act in said_out_of_scope:
        recs.append(
            _rec(
                "warn",
                f"decided action {act} OUTSIDE declared capability_scope",
                "the agent said it would do more than it declared",
            )
        )
    if process_spawned:
        recs.append(
            _rec(
                "info",
                "child process lifecycle (fork/exec)",
                "capture the child pid tree so a spawned helper is attributed to this agent",
            )
        )
    for path in sensitive_opens[:5]:
        recs.append(
            _rec(
                "info",
                f"file access {path}",
                "non-library file access -- log for the data-access audit",
            )
        )
    for srv in dialed:
        if srv in declared_set:
            recs.append(
                _rec(
                    "info",
                    f"connect to declared server {srv}",
                    "the legitimate side-effect wire -- log for the audit trail",
                )
            )
    recs.sort(key=lambda r: (_SEVERITY_ORDER.get(r["severity"], 9), r["log"]))

    worst = recs[0]["severity"] if recs else "info"
    verdict = "coherent" if coherent else "DIVERGENT"
    analysis = (
        f"{verdict}: planned systems {sorted(declared_set) or 'none'}, "
        f"dialed {dialed or 'none'}, undeclared egress {len(undeclared_egress)}, "
        f"undeclared dns {len(undeclared_dns)}, "
        f"{'process spawn' if process_spawned else 'no spawn'}. Top severity: {worst}."
    )

    return {
        "agent_id": agent_id,
        "identified": identified,
        "seen_kinds": seen_kinds,
        "planned": {"systems": sorted(declared_set), "scope": sorted(set(declared_scope))},
        "said": {"actions": sorted(set(decided_actions))} if decided_actions is not None else None,
        "done": {
            "dialed_servers": dialed,
            "undeclared_egress": undeclared_egress,
            "undeclared_dns": undeclared_dns,
            "process_spawned": process_spawned,
            "sensitive_opens": sensitive_opens,
        },
        "coherent": coherent,
        "logging_recommendations": recs,
        "analysis": analysis,
    }


def analyze_recording(
    annotated: dict,
    *,
    declared_by_agent: dict[str, dict],
) -> list[dict]:
    """Run `analyze_agent` for every agent in an annotated recording (the
    `wire_named` map from `netmap.annotate_recording`). `declared_by_agent` maps
    agent_id -> {scope, systems, decided}. Pure, sorted by agent_id."""
    wire_named = annotated.get("wire_named", {})
    out = []
    for agent_id in sorted(wire_named):
        d = declared_by_agent.get(agent_id, {})
        out.append(
            analyze_agent(
                agent_id,
                declared_scope=list(d.get("scope", [])),
                declared_systems=list(d.get("systems", [])),
                wire_annotations=wire_named[agent_id],
                decided_actions=d.get("decided"),
            )
        )
    return out
