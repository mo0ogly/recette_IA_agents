"""mcp mock handler -- MAF tool invocation (2 actions).

A realistic deterministic double of an MCP tool/handoff surface. Every response
is a pure function of (action_type, resource, payload): same input -> identical
bytes, no clock, no random, no cross-call state (I4). See ``_realism`` for the
shared primitives. These responses are only produced AFTER the gateway approves
an escalate-class MCP action (I6); the handler itself performs no governance.
"""

from __future__ import annotations

from ._realism import derived_int, digest, envelope, ref

_DOMAIN = "mcp"
_KNOWN_ACTIONS = frozenset(("invoke_tool", "handoff"))


def handle(action_type: str, resource: str, payload: dict) -> dict | None:
    """Return a realistic deterministic response, or ``None`` for an unknown
    action."""
    if action_type not in _KNOWN_ACTIONS:
        return None
    dig = digest(_DOMAIN, action_type, resource, payload)
    base = envelope(action_type, resource, dig)

    if action_type == "invoke_tool":
        return {
            **base,
            "status": "invoked",
            "tool": str(payload.get("tool") or resource),
            "call_id": ref("call_", dig),
            "output_tokens": derived_int(dig, 1, 4000),
            "approved": bool(payload.get("approved", False)),
        }
    # handoff
    return {
        **base,
        "status": "transferred",
        "from_agent": str(payload.get("from") or resource),
        "to_agent": str(payload.get("to") or "target-agent"),
        "transfer_id": ref("ho_", dig),
    }
