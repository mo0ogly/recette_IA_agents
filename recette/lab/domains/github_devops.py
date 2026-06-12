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


def _derived_int(action_type: str, resource: str, payload: dict, lo: int, hi: int) -> int:
    """Stable small integer in [lo, hi) derived from the input (I4).

    Used for synthetic issue/PR numbers: deterministic, no counters, no clock.
    """
    digest = _result_id(action_type, resource, payload)
    span = hi - lo
    return lo + (int(digest, 16) % span)


def _read_repo(action_type: str, resource: str, payload: dict, rid: str) -> dict:
    return {
        "action": action_type,
        "resource": resource,
        "repository": {"full_name": resource, "default_branch": "main"},
        "result_id": rid,
    }


def _list_repos(action_type: str, resource: str, payload: dict, rid: str) -> dict:
    # Deterministic synthetic listing derived from the resource (the owner/org).
    repositories = [f"{resource}/{rid[:4]}-{idx}" for idx in range(3)]
    return {
        "action": action_type,
        "resource": resource,
        "repositories": repositories,
        "result_id": rid,
    }


def _open_issue(action_type: str, resource: str, payload: dict, rid: str) -> dict:
    return {
        "action": action_type,
        "resource": resource,
        "issue": {
            "number": _derived_int(action_type, resource, payload, 1, 10000),
            "state": "open",
        },
        "result_id": rid,
    }


def _comment_issue(action_type: str, resource: str, payload: dict, rid: str) -> dict:
    return {
        "action": action_type,
        "resource": resource,
        "comment_id": _result_id(action_type, resource, payload),
        "result_id": rid,
    }


def _open_pr(action_type: str, resource: str, payload: dict, rid: str) -> dict:
    return {
        "action": action_type,
        "resource": resource,
        "pull_request": {
            "number": _derived_int(action_type, resource, payload, 1, 10000),
            "state": "open",
        },
        "result_id": rid,
    }


def _merge_pr(action_type: str, resource: str, payload: dict, rid: str) -> dict:
    return {
        "action": action_type,
        "resource": resource,
        "merged": True,
        "result_id": rid,
    }


def _push(action_type: str, resource: str, payload: dict, rid: str) -> dict:
    return {
        "action": action_type,
        "resource": resource,
        "pushed": True,
        "commit": _result_id(action_type, resource, payload),
        "result_id": rid,
    }


def _manage_webhook(action_type: str, resource: str, payload: dict, rid: str) -> dict:
    return {
        "action": action_type,
        "resource": resource,
        "webhook_id": _result_id(action_type, resource, payload),
        "result_id": rid,
    }


# Canonical read/standard github action_types (recette-corpus.md mapping) the
# mock domain simulates so read-only agents are testable in lab mode. Each
# builder is pure and deterministic (ids derived from sha256 of inputs -- I4).
_CANONICAL_HANDLERS = {
    "read_repo": _read_repo,
    "list_repos": _list_repos,
    "open_issue": _open_issue,
    "comment_issue": _comment_issue,
    "open_pr": _open_pr,
    "merge_pr": _merge_pr,
    "push": _push,
    "manage_webhook": _manage_webhook,
}


def handle(action_type: str, resource: str, payload: dict) -> dict | None:
    """Return a deterministic response dict, or None when action is unknown.

    Risky/write actions (``_ACTION_FIELDS``) keep their simulated envelope.
    Canonical read/standard actions (``_CANONICAL_HANDLERS``) return an
    action-specific shape. Unknown action_type -> None (404 at the server).
    """
    fields = _ACTION_FIELDS.get(action_type)
    if fields is not None:
        response = {
            "action": action_type,
            "resource": resource,
            "status": "simulated",
            "result_id": _result_id(action_type, resource, payload),
        }
        response.update(fields)
        return response
    builder = _CANONICAL_HANDLERS.get(action_type)
    if builder is not None:
        return builder(action_type, resource, payload, _result_id(action_type, resource, payload))
    return None
