"""mcp domain action specs -- MAF tool invocation governance.

A MAF agent invoking an MCP tool or handing off to another agent is an external
side effect (I5). AgentRail governs it deny-by-default: a privileged role
escalates (human approval, I6), any other role is denied. This is intentionally
stricter than the agent's own declared approval mode -- the runtime never trusts
the agent's self-declared `require_approval`; it escalates the side effect itself
(McpServerApprovalMode in agent_framework_declarative._models is the agent's
claim; this catalog is the governance posture).

Verdict mapping convention (mirrors okta): ESC rows escalate for the privileged
role and deny for everyone else; privileged_roles = ("tool_operator",).
"""

from __future__ import annotations

from ...events import PolicyVerdict
from ..model import ActionSpec, RiskLevel

TARGET_SYSTEM = "mcp"

_TOOL_OPERATOR = ("tool_operator",)


def _escalate(action_type: str, risk_level: RiskLevel, description: str) -> ActionSpec:
    """ESC row: escalate for tool_operator, deny for everyone else (deny-by-default)."""
    return ActionSpec(
        target_system=TARGET_SYSTEM,
        action_type=action_type,
        risk_level=risk_level,
        verdict_privileged=PolicyVerdict.ESCALATE,
        verdict_default=PolicyVerdict.DENY,
        privileged_roles=_TOOL_OPERATOR,
        description=description,
    )


ACTIONS: tuple[ActionSpec, ...] = (
    _escalate(
        "invoke_tool",
        RiskLevel.HIGH,
        "Invoke an MCP tool (external side effect): escalate for human approval (I6).",
    ),
    _escalate(
        "handoff",
        RiskLevel.HIGH,
        "Hand off control to another agent: escalate for human approval (I6).",
    ),
)
