"""mcp mock handler -- MAF tool invocation (2 actions).

Handlers are pure and deterministic: same input -> identical response bytes
(stable ids derived from sha256 of inputs, no clock, no random -- I4). These
responses are only produced AFTER the gateway approves an escalate-class MCP
action (I6); the handler itself performs no governance.
"""

from __future__ import annotations

import hashlib
import json

# Action-specific deterministic fields merged into the simulated response.
_ACTION_FIELDS: dict[str, dict[str, str]] = {
    "invoke_tool": {"tool_state": "invoked"},
    "handoff": {"handoff_state": "transferred"},
}


def handle(action_type: str, resource: str, payload: dict) -> dict | None:
    """Return a deterministic response dict, or None when action is unknown."""
    extra = _ACTION_FIELDS.get(action_type)
    if extra is None:
        return None
    material = f"mcp:{action_type}:{resource}:{json.dumps(payload, sort_keys=True)}"
    result_id = hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]
    response: dict = {
        "action": action_type,
        "resource": resource,
        "result_id": result_id,
        **extra,
    }
    return response
