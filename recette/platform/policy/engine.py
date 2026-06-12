"""Pure policy decision function (I2/I4).

decide() reads ONLY its arguments: no clock, no I/O, no global state. Unknown
action, unknown role or missing rule resolves to DENY. The caller (gateway)
catches any exception and converts it to DENY plus an audited error event
(failure-modes.md: policy engine down -> default DENY, never fail-open).
"""

from __future__ import annotations

from ..catalog import Catalog
from ..catalog.model import RiskLevel
from ..events import PlatformActionEvent, PolicyVerdict
from .model import Decision, PolicyVersion


def decide(event: PlatformActionEvent, policy: PolicyVersion, catalog: Catalog) -> Decision:
    """Evaluate one normalized event against one policy version. Pure function."""
    spec = catalog.get(event.target_system, event.action_type)
    if spec is None:
        # Action not governed by the catalog: deny-by-default.
        return Decision(
            verdict=PolicyVerdict.DENY,
            policy_version=policy.version,
            rule_id=None,
            risk_level=RiskLevel.CRITICAL,
        )

    rule = policy.rule_for(event.target_system, event.action_type, event.role)
    if rule is None:
        # No explicit rule for this role: catalog default verdict (deny for the
        # whole sensitive catalog), still recorded against the policy version.
        return Decision(
            verdict=spec.verdict_default,
            policy_version=policy.version,
            rule_id=None,
            risk_level=spec.risk_level,
        )

    return Decision(
        verdict=rule.verdict,
        policy_version=policy.version,
        rule_id=rule.rule_id,
        risk_level=rule.risk_level,
    )
