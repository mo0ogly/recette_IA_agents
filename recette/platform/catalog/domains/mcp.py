"""mcp domain action specs -- MAF tool invocation governance.

A MAF agent invoking an MCP tool or handing off to another agent is an external
side effect (I5). inspect_ia_agents governs it deny-by-default: a privileged role
escalates (human approval, I6), any other role is denied. This is intentionally
stricter than the agent's own declared approval mode -- the runtime never trusts
the agent's self-declared `require_approval`; it escalates the side effect itself
(McpServerApprovalMode in agent_framework_declarative._models is the agent's
claim; this catalog is the governance posture).

Criticality (Annex C) is the AgentRail default posture, independent from the
implemented verdict; see catalog/model.py::Criticality. MCP tool governance is
not in Annex C's initial 118-action referential, so both rows are C2 (systematic
escalation), matching the escalate verdict.

Verdict mapping convention (mirrors okta): ESC rows escalate for the privileged
role and deny for everyone else; privileged_roles = ("tool_operator",).
"""

from __future__ import annotations

from ...events import PolicyVerdict
from ..model import ActionSpec, Criticality, RiskLevel

TARGET_SYSTEM = "mcp"

_TOOL_OPERATOR = ("tool_operator",)


def _escalate(
    action_type: str, criticality: Criticality, risk_level: RiskLevel, description: str
) -> ActionSpec:
    """ESC row: escalate for tool_operator, deny for everyone else (deny-by-default)."""
    return ActionSpec(
        target_system=TARGET_SYSTEM,
        action_type=action_type,
        risk_level=risk_level,
        criticality=criticality,
        verdict_privileged=PolicyVerdict.ESCALATE,
        verdict_default=PolicyVerdict.DENY,
        privileged_roles=_TOOL_OPERATOR,
        description=description,
    )


ACTIONS: tuple[ActionSpec, ...] = (
    _escalate(
        "invoke_tool",
        Criticality.C2,
        RiskLevel.HIGH,
        "Invoke an MCP tool (external side effect): escalate for human approval (I6).",
    ),
    _escalate(
        "handoff",
        Criticality.C2,
        RiskLevel.HIGH,
        "Hand off control to another agent: escalate for human approval (I6).",
    ),
)
