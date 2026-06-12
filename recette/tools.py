"""LB2 -- tool registry bridging LLM tool calls to the mediated forge.

A Lane B agent's tools ARE the canonical actions. This module turns a capability set into
the ToolSpec list the LLM sees, and executes a chosen tool call through the forge (I5),
producing an AgentAction (same shape as Lane A). The forge is already surface-agnostic, so
this works for every target_system (github/gitlab/openapi/temporal/mcp).
"""

from __future__ import annotations

from .events import ActionType, AgentAction
from .forge import GitForge
from .llm import LlmDecision, ToolSpec

# One-line description per canonical action, shown to the LLM as the tool's purpose.
_ACTION_DESCRIPTIONS: dict[str, str] = {
    "read_repo": "Read repository/project metadata (read-only).",
    "list_repos": "List repositories/projects (read-only).",
    "read_ci": "Read CI/CD pipeline status (read-only).",
    "open_issue": "Open an issue (bounded write).",
    "comment_issue": "Comment on an issue (bounded write).",
    "open_pr": "Open a pull/merge request (bounded write).",
    "merge_pr": "Merge a pull/merge request (high blast-radius write).",
    "push": "Commit to the default branch (high blast-radius write).",
    "manage_webhook": "Create or modify a webhook (high blast-radius write).",
    "manage_release": "Create or modify a release (high blast-radius write).",
    "trigger_ci": "Trigger a CI/CD pipeline run (high blast-radius write).",
}

# Coarse risk class per canonical git action, used to order/badge the catalog.
_ACTION_KIND: dict[str, str] = {
    "read_repo": "read",
    "list_repos": "read",
    "read_ci": "read",
    "open_issue": "bounded_write",
    "comment_issue": "bounded_write",
    "open_pr": "bounded_write",
    "merge_pr": "high_write",
    "push": "high_write",
    "manage_webhook": "high_write",
    "manage_release": "high_write",
    "trigger_ci": "high_write",
}

# Target systems whose executable agent actions are the canonical git set
# (the discovery corpus is built on these); other systems use the governance
# catalog actions (okta, finance, ...), executed deterministically by the forge.
_GIT_SYSTEMS: tuple[str, ...] = ("github", "gitlab")


def _kind_for_spec(action_type: str, risk_level: str) -> str:
    """Read/bounded_write/high_write class for a governance catalog action."""
    from .events import Mode, mode_for_action

    if mode_for_action(action_type) is Mode.READ:
        return "read"
    return "high_write" if risk_level in ("high", "critical") else "bounded_write"


def _multi_system_catalog() -> list[dict[str, str]]:
    """All executable agent actions across the 11 systems: the canonical git
    actions for github/gitlab, plus the governance catalog for every other
    system. Cached after first build (pure, deterministic)."""
    from .platform.catalog import load_catalog

    rows: list[dict[str, str]] = []
    for system in _GIT_SYSTEMS:
        for name, desc in _ACTION_DESCRIPTIONS.items():
            rows.append(
                {
                    "target_system": system,
                    "action": name,
                    "description": desc,
                    "kind": _ACTION_KIND.get(name, "bounded_write"),
                }
            )
    for spec in load_catalog().all():
        if spec.target_system in _GIT_SYSTEMS:
            continue
        rows.append(
            {
                "target_system": spec.target_system,
                "action": spec.action_type,
                "description": spec.description,
                "kind": _kind_for_spec(spec.action_type, spec.risk_level),
            }
        )
    return rows


# Every action name the forge/tools accept: canonical git actions plus every
# governance catalog action. Built once at import (pure data).
def _known_actions() -> frozenset[str]:
    names = {a.value for a in ActionType}
    names.update(row["action"] for row in _multi_system_catalog())
    return frozenset(names)


_KNOWN_ACTIONS: frozenset[str] = _known_actions()

# Description lookup spanning git + governance actions, for tool specs.
_ALL_DESCRIPTIONS: dict[str, str] = {
    **{row["action"]: row["description"] for row in _multi_system_catalog()},
    **_ACTION_DESCRIPTIONS,
}


def agent_action_catalog() -> list[dict[str, str]]:
    """Executable agent-action catalog across the 11 systems, stable order
    (by target_system, then read -> bounded_write -> high_write, then name)."""
    order = {"read": 0, "bounded_write": 1, "high_write": 2}
    return sorted(
        _multi_system_catalog(),
        key=lambda a: (a["target_system"], order.get(a["kind"], 1), a["action"]),
    )


def tool_spec(action: str) -> ToolSpec:
    """The ToolSpec for one canonical action (a 'resource' target + free-form params)."""
    if action not in _KNOWN_ACTIONS:
        raise ValueError(f"unknown action {action!r}")
    return ToolSpec(
        name=action,
        description=_ALL_DESCRIPTIONS.get(action, action),
        parameters={
            "type": "object",
            "properties": {
                "resource": {
                    "type": "string",
                    "description": "Target resource, e.g. 'acme/widgets' or an endpoint id.",
                },
                "params": {"type": "object", "description": "Optional action parameters."},
            },
            "required": ["resource"],
        },
    )


def build_tools(actions: list[str]) -> list[ToolSpec]:
    """Toolset exposed to the agent for its capability set (deduped, stable order)."""
    return [tool_spec(a) for a in sorted(set(actions))]


def execute_tool(
    forge: GitForge,
    *,
    agent_id: str,
    principal: str,
    target_system: str,
    decision: LlmDecision,
    approved: bool = False,
) -> AgentAction:
    """Execute the tool chosen by the LLM through the forge, returning the AgentAction.

    Raises ValueError if the decision is not a tool call or names an unknown action.
    """
    if not decision.is_tool_call or decision.tool_name is None:
        raise ValueError("decision is not a tool call")
    if decision.tool_name not in _KNOWN_ACTIONS:
        raise ValueError(f"unknown tool {decision.tool_name!r}")
    args = dict(decision.tool_args or {})
    resource = str(args.get("resource", ""))
    params = args.get("params")
    if not isinstance(params, dict):
        params = {k: v for k, v in args.items() if k != "resource"}
    return forge.execute(
        agent_id=agent_id,
        principal=principal,
        target_system=target_system,
        action_type=decision.tool_name,
        resource=resource,
        approved=approved,
        params=params,
    )
