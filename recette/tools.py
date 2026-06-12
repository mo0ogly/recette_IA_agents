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

_KNOWN_ACTIONS: frozenset[str] = frozenset(a.value for a in ActionType)

# Coarse risk class per action, used to order and badge the action catalog.
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


def agent_action_catalog() -> list[dict[str, str]]:
    """The canonical agent-action catalog (what an agent can be made to do),
    in a stable read -> bounded_write -> high_write order."""
    order = {"read": 0, "bounded_write": 1, "high_write": 2}
    actions = [
        {
            "action": name,
            "description": _ACTION_DESCRIPTIONS[name],
            "kind": _ACTION_KIND.get(name, "bounded_write"),
        }
        for name in _ACTION_DESCRIPTIONS
    ]
    return sorted(actions, key=lambda a: (order.get(a["kind"], 1), a["action"]))


def tool_spec(action: str) -> ToolSpec:
    """The ToolSpec for one canonical action (a 'resource' target + free-form params)."""
    if action not in _KNOWN_ACTIONS:
        raise ValueError(f"unknown action {action!r}")
    return ToolSpec(
        name=action,
        description=_ACTION_DESCRIPTIONS.get(action, action),
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
