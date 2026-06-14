"""cloud domain action specs -- W8 Cloud / infrastructure (13 actions).

Source of truth: docs/tracking/PLAN_high-risk-action-catalog_2026-06-12.md, section W8.
Criticality (Annex C) is the AgentRail default posture, independent from the
implemented verdict; see catalog/model.py::Criticality.
Verdict mapping convention:
- ESC and DENY/ESC rows: privileged role escalates, any other role is denied
  (deny-by-default), privileged_roles = ("cloud_admin",).
- DENY rows: denied for every role, privileged_roles = ().
"""

from __future__ import annotations

from ...events import PolicyVerdict
from ..model import ActionSpec, Criticality, RiskLevel

TARGET_SYSTEM = "cloud"

_CLOUD_ADMIN = ("cloud_admin",)


def _escalate(
    action_type: str, criticality: Criticality, risk_level: RiskLevel, description: str
) -> ActionSpec:
    """ESC / DENY-ESC row: escalate for cloud_admin, deny for everyone else."""
    return ActionSpec(
        target_system=TARGET_SYSTEM,
        action_type=action_type,
        risk_level=risk_level,
        criticality=criticality,
        verdict_privileged=PolicyVerdict.ESCALATE,
        verdict_default=PolicyVerdict.DENY,
        privileged_roles=_CLOUD_ADMIN,
        description=description,
    )


def _deny(
    action_type: str, criticality: Criticality, risk_level: RiskLevel, description: str
) -> ActionSpec:
    """Pure DENY row: denied for every role, no privileged escape hatch."""
    return ActionSpec(
        target_system=TARGET_SYSTEM,
        action_type=action_type,
        risk_level=risk_level,
        criticality=criticality,
        verdict_privileged=PolicyVerdict.DENY,
        verdict_default=PolicyVerdict.DENY,
        privileged_roles=(),
        description=description,
    )


def _allow(
    action_type: str, criticality: Criticality, risk_level: RiskLevel, description: str
) -> ActionSpec:
    """Routine authorized read row: allow for cloud_admin, deny for everyone else."""
    return ActionSpec(
        target_system=TARGET_SYSTEM,
        action_type=action_type,
        risk_level=risk_level,
        criticality=criticality,
        verdict_privileged=PolicyVerdict.ALLOW,
        verdict_default=PolicyVerdict.DENY,
        privileged_roles=_CLOUD_ADMIN,
        description=description,
    )


ACTIONS: tuple[ActionSpec, ...] = (
    _allow(
        "read_resource_inventory",
        Criticality.C4,
        RiskLevel.LOW,
        "List cloud resource inventory and status (read-only).",
    ),
    _escalate(
        "delete_database", Criticality.C1, RiskLevel.CRITICAL, "Delete a managed database instance."
    ),
    _escalate(
        "delete_s3_bucket",
        Criticality.C1,
        RiskLevel.CRITICAL,
        "Delete an S3 bucket and its contents.",
    ),
    _escalate(
        "make_bucket_public",
        Criticality.C1,
        RiskLevel.CRITICAL,
        "Make a storage bucket publicly accessible.",
    ),
    _escalate(
        "modify_security_group",
        Criticality.C2,
        RiskLevel.CRITICAL,
        "Modify firewall rules of a security group.",
    ),
    _escalate(
        "open_sensitive_port",
        Criticality.C1,
        RiskLevel.CRITICAL,
        "Open a sensitive network port to inbound traffic.",
    ),
    _deny(
        "delete_backups",
        Criticality.C1,
        RiskLevel.CRITICAL,
        "Delete backup archives of cloud resources.",
    ),
    _escalate(
        "modify_k8s_config",
        Criticality.C2,
        RiskLevel.HIGH,
        "Modify a Kubernetes cluster configuration.",
    ),
    _escalate(
        "delete_critical_pod", Criticality.C2, RiskLevel.HIGH, "Delete a critical Kubernetes pod."
    ),
    _escalate(
        "deploy_unvalidated_image",
        Criticality.C1,
        RiskLevel.HIGH,
        "Deploy a container image that has not been validated.",
    ),
    _escalate(
        "modify_env_variable",
        Criticality.C3,
        RiskLevel.HIGH,
        "Modify an environment variable of a deployed service.",
    ),
    _deny("delete_kms_key", Criticality.C1, RiskLevel.CRITICAL, "Delete a KMS encryption key."),
    _escalate(
        "modify_cloud_iam",
        Criticality.C2,
        RiskLevel.CRITICAL,
        "Modify cloud IAM roles or permission bindings.",
    ),
)
