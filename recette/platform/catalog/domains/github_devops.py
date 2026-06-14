"""github_devops domain action specs (W2 of the high-risk action catalog plan).

14 sensitive GitHub / DevOps actions. Rows marked ESC or DENY/ESC in the plan
escalate for the privileged role (devops_admin) and are denied for any other
role (deny-by-default). Criticality (Annex C) is the AgentRail default posture,
independent from the implemented verdict; see catalog/model.py::Criticality.
"""

from __future__ import annotations

from ...events import PolicyVerdict
from ..model import ActionSpec, Criticality, RiskLevel

TARGET_SYSTEM = "github"

_PRIVILEGED_ROLES = ("devops_admin",)


def _spec(
    action_type: str, criticality: Criticality, risk_level: RiskLevel, description: str
) -> ActionSpec:
    """Build one W2 row: ESC / DENY-ESC -> escalate for devops_admin, deny otherwise."""
    return ActionSpec(
        target_system=TARGET_SYSTEM,
        action_type=action_type,
        risk_level=risk_level,
        criticality=criticality,
        verdict_privileged=PolicyVerdict.ESCALATE,
        verdict_default=PolicyVerdict.DENY,
        privileged_roles=_PRIVILEGED_ROLES,
        description=description,
    )


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
        privileged_roles=_PRIVILEGED_ROLES,
        description=description,
    )


ACTIONS: tuple[ActionSpec, ...] = (
    _allow(
        "read_repo_metadata",
        Criticality.C4,
        RiskLevel.LOW,
        "Read repository metadata and CI status (read-only).",
    ),
    _spec(
        "delete_repository",
        Criticality.C1,
        RiskLevel.CRITICAL,
        "Permanently delete a repository and its history.",
    ),
    _spec(
        "make_repo_public",
        Criticality.C1,
        RiskLevel.CRITICAL,
        "Change a private repository visibility to public.",
    ),
    _spec(
        "modify_cicd_secrets",
        Criticality.C2,
        RiskLevel.CRITICAL,
        "Create, update or remove CI/CD pipeline secrets.",
    ),
    _spec(
        "deploy_production",
        Criticality.C2,
        RiskLevel.HIGH,
        "Trigger a deployment to the production environment.",
    ),
    _spec(
        "modify_protected_branch",
        Criticality.C2,
        RiskLevel.HIGH,
        "Push or force changes to a protected branch.",
    ),
    _spec(
        "disable_branch_protection",
        Criticality.C1,
        RiskLevel.CRITICAL,
        "Disable branch protection rules on a repository.",
    ),
    _spec(
        "merge_pr_without_review",
        Criticality.C1,
        RiskLevel.HIGH,
        "Merge a pull request bypassing required reviews.",
    ),
    _spec(
        "create_github_token",
        Criticality.C3,
        RiskLevel.HIGH,
        "Create a new GitHub access token.",
    ),
    _spec(
        "add_deploy_key",
        Criticality.C2,
        RiskLevel.HIGH,
        "Add an SSH deploy key to a repository.",
    ),
    _spec(
        "modify_gh_actions_workflow",
        Criticality.C2,
        RiskLevel.HIGH,
        "Modify a GitHub Actions workflow definition.",
    ),
    _spec(
        "delete_prod_environment",
        Criticality.C1,
        RiskLevel.CRITICAL,
        "Delete the production deployment environment.",
    ),
    _spec(
        "modify_org_permissions",
        Criticality.C2,
        RiskLevel.CRITICAL,
        "Change organization-level roles or permissions.",
    ),
    _spec(
        "add_external_collaborator",
        Criticality.C3,
        RiskLevel.HIGH,
        "Grant repository access to an external collaborator.",
    ),
)
