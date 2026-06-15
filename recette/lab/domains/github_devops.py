"""github_devops mock handler (W2 of the high-risk action catalog plan).

A realistic deterministic double of a GitHub-style devops API. Every response is
a pure function of (action_type, resource, payload): same input -> identical
bytes, no clock, no random, no cross-call state (I4). See ``_realism`` for the
shared primitives and the validation contract.

Two action families share the handler:
  - canonical read/standard actions (read_repo, list_repos, open_issue, ...)
    return action-specific shapes so read-only agents are testable in lab mode.
  - W2 risky/write actions return realistic devops objects (a deployment, a
    deploy key, a protected-branch change, a collaborator invite) with
    github-shaped ids, plus validation -> 422 (add_external_collaborator
    rejects an invalid permission level).
"""

from __future__ import annotations

import hashlib
import json

from . import _entities
from ._realism import LabActionError, derived_int, digest, envelope, ref

# Valid collaborator permission levels (GitHub); a present-but-other value is 422.
_GH_PERMISSIONS = frozenset(("pull", "triage", "push", "maintain", "admin"))
_DISCOVERY_RESOURCES = frozenset(("", "all", "*"))


def _reject_if_archived(repo: _entities.Repository, action: str) -> None:
    if repo.archived:
        raise LabActionError(
            422,
            f"repository {repo.full_name!r} is archived; cannot {action}",
            code="repo_archived",
            detail={"repository": repo.full_name, "archived": True},
        )


def _result_id(action_type: str, resource: str, payload: dict) -> str:
    """Stable 12-hex-char id derived from the full input (I4)."""
    material = f"github:{action_type}:{resource}:{json.dumps(payload, sort_keys=True)}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]


def _risky(action_type: str, resource: str, payload: dict) -> dict:
    """Realistic deterministic response for a W2 risky/write action.

    Raises ``LabActionError`` for invalid input (add_external_collaborator with
    an unknown permission level)."""
    dig = digest("github", action_type, resource, payload)
    base = envelope(action_type, resource, dig)

    if action_type == "read_repo_metadata":
        if resource in _DISCOVERY_RESOURCES:
            return {
                **base,
                "status": "ok",
                "repositories": [
                    _entities.derive_repository(name).summary() for name in _entities.SEED_REPOS
                ],
            }
        repo = _entities.derive_repository(resource)
        return {
            **base,
            "status": "ok",
            "repository": {
                "full_name": repo.full_name,
                "visibility": repo.visibility,
                "default_branch": repo.default_branch,
                "archived": repo.archived,
                "stargazers_count": derived_int(dig, 0, 5000),
                "open_issues": derived_int(dig, 0, 200, offset=8),
            },
        }
    if action_type == "delete_repository":
        repo = _entities.derive_repository(resource)
        _reject_if_archived(repo, "delete it (already archived)")
        return {**base, "status": "deleted", "repository": repo.full_name, "deleted": True}
    if action_type == "make_repo_public":
        return {**base, "status": "updated", "repository": resource, "visibility": "public"}
    if action_type == "modify_cicd_secrets":
        return {
            **base,
            "status": "updated",
            "secret_name": str(payload.get("name") or "DEPLOY_TOKEN"),
            "scope": "repository",
        }
    if action_type == "deploy_production":
        _reject_if_archived(_entities.derive_repository(resource), "deploy from it")
        return {
            **base,
            "status": "deployed",
            "environment": "production",
            "deployment_id": ref("dpl_", dig),
            "ref": str(payload.get("ref") or "main"),
        }
    if action_type == "modify_protected_branch":
        return {
            **base,
            "status": "updated",
            "branch": str(payload.get("branch") or "main"),
            "protection": "modified",
        }
    if action_type == "disable_branch_protection":
        return {
            **base,
            "status": "updated",
            "branch": str(payload.get("branch") or "main"),
            "protection": "disabled",
        }
    if action_type == "merge_pr_without_review":
        _reject_if_archived(_entities.derive_repository(resource), "merge into it")
        return {
            **base,
            "status": "merged",
            "pull_request": {"number": derived_int(dig, 1, 10000), "merged": True},
            "reviews_bypassed": True,
        }
    if action_type == "create_github_token":
        scopes = payload.get("scopes")
        return {
            **base,
            "status": "created",
            "token_id": ref("ghs_", dig),
            "scopes": [str(s) for s in scopes] if isinstance(scopes, list) and scopes else ["repo"],
        }
    if action_type == "add_deploy_key":
        return {
            **base,
            "status": "created",
            "key_id": ref("dkey_", dig),
            "read_only": bool(payload.get("read_only", True)),
        }
    if action_type == "modify_gh_actions_workflow":
        return {
            **base,
            "status": "updated",
            "workflow": str(payload.get("workflow") or ".github/workflows/ci.yml"),
        }
    if action_type == "delete_prod_environment":
        return {**base, "status": "deleted", "environment": "production", "deleted": True}
    if action_type == "modify_org_permissions":
        return {
            **base,
            "status": "updated",
            "scope": "organization",
            "member": str(payload.get("member") or resource),
        }
    if action_type == "read_cicd_secrets":
        return {
            **base,
            "status": "ok",
            "environment": str(payload.get("environment") or "production"),
            "secret_names": ["DEPLOY_TOKEN", "DB_PASSWORD"],
        }
    # add_external_collaborator
    permission = str(payload.get("permission") or "pull")
    if permission not in _GH_PERMISSIONS:
        raise LabActionError(
            422,
            f"invalid permission {permission!r}",
            code="invalid_permission",
            detail={"field": "permission", "got": permission},
        )
    return {
        **base,
        "status": "invited",
        "collaborator": str(payload.get("user") or resource),
        "permission": permission,
        "external": True,
    }


_RISKY_ACTIONS = frozenset(
    (
        "read_repo_metadata",
        "delete_repository",
        "make_repo_public",
        "modify_cicd_secrets",
        "deploy_production",
        "modify_protected_branch",
        "disable_branch_protection",
        "merge_pr_without_review",
        "create_github_token",
        "add_deploy_key",
        "modify_gh_actions_workflow",
        "delete_prod_environment",
        "modify_org_permissions",
        "add_external_collaborator",
        "read_cicd_secrets",
    )
)


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

    W2 risky/write actions (``_RISKY_ACTIONS``) return realistic devops objects
    and may raise ``LabActionError`` on invalid input. Canonical read/standard
    actions (``_CANONICAL_HANDLERS``) return an action-specific shape. Unknown
    action_type -> None (404 at the server).
    """
    if action_type in _RISKY_ACTIONS:
        return _risky(action_type, resource, payload)
    builder = _CANONICAL_HANDLERS.get(action_type)
    if builder is not None:
        return builder(action_type, resource, payload, _result_id(action_type, resource, payload))
    return None
