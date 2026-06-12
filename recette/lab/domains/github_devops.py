"""github_devops mock handler (W2 of the high-risk action catalog plan).

Handlers are pure and deterministic: same input -> identical response bytes
(stable ids derived from sha256 of inputs, no clock, no random -- I4).
"""

from __future__ import annotations

import hashlib
import json

# Deterministic action-specific fields merged into the simulated response.
# Static data only: no clock, no random, no module state (I4).
_ACTION_FIELDS: dict[str, dict] = {
    "delete_repository": {"repository_deleted": True},
    "make_repo_public": {"visibility": "public"},
    "modify_cicd_secrets": {"secrets_scope": "cicd"},
    "deploy_production": {"environment": "production"},
    "modify_protected_branch": {"branch_protection": "modified"},
    "disable_branch_protection": {"branch_protection": "disabled"},
    "merge_pr_without_review": {"merged": True, "reviews_bypassed": True},
    "create_github_token": {"token_kind": "github_token"},
    "add_deploy_key": {"key_kind": "deploy_key"},
    "modify_gh_actions_workflow": {"workflow_modified": True},
    "delete_prod_environment": {"environment_deleted": "production"},
    "modify_org_permissions": {"permissions_scope": "organization"},
    "add_external_collaborator": {"collaborator_scope": "external"},
}


def _result_id(action_type: str, resource: str, payload: dict) -> str:
    """Stable 12-hex-char id derived from the full input (I4)."""
    material = f"github:{action_type}:{resource}:{json.dumps(payload, sort_keys=True)}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]


def handle(action_type: str, resource: str, payload: dict) -> dict | None:
    """Return a deterministic response dict, or None when action is unknown."""
    fields = _ACTION_FIELDS.get(action_type)
    if fields is None:
        return None
    response = {
        "action": action_type,
        "resource": resource,
        "status": "simulated",
        "result_id": _result_id(action_type, resource, payload),
    }
    response.update(fields)
    return response
