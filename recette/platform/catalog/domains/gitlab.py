"""gitlab domain action specs -- git-family read actions (governed catalog).

gitlab is a git-family double of github (shares the canonical git vocabulary,
recette/tools.py _GIT_SYSTEMS). Only the read actions are governed here: a
read-only git agent listing/reading projects is an authorized routine action for
the devops_admin role (allow, least-privilege), denied for everyone else. Write
git actions stay outside the governance catalog (handled by the lab git double).
Promoted from the multidomain scenario EXTRA_SPECS. Criticality (Annex C axis) is
the AgentRail default posture; see catalog/model.py::Criticality.
"""

from __future__ import annotations

from ...events import PolicyVerdict
from ..model import ActionSpec, Criticality, RiskLevel

TARGET_SYSTEM = "gitlab"

_DEVOPS_ADMIN = ("devops_admin",)


def _allow(
    action_type: str, criticality: Criticality, risk_level: RiskLevel, description: str
) -> ActionSpec:
    """Routine authorized read row: allow for devops_admin, deny for everyone else."""
    return ActionSpec(
        target_system=TARGET_SYSTEM,
        action_type=action_type,
        risk_level=risk_level,
        criticality=criticality,
        verdict_privileged=PolicyVerdict.ALLOW,
        verdict_default=PolicyVerdict.DENY,
        privileged_roles=_DEVOPS_ADMIN,
        description=description,
    )


ACTIONS: tuple[ActionSpec, ...] = (
    _allow(
        "read_repo",
        Criticality.C4,
        RiskLevel.LOW,
        "Read a GitLab project (read-only).",
    ),
    _allow(
        "list_repos",
        Criticality.C4,
        RiskLevel.LOW,
        "List GitLab projects of a group (read-only).",
    ),
)
