"""gitlab mock handler -- git family (canonical git actions, GitLab-flavoured).

gitlab shares the canonical git action vocabulary with github (read_repo,
list_repos, open_issue, comment_issue, open_pr, merge_pr, push, manage_webhook;
see recette/tools.py ``_GIT_SYSTEMS``), so read-only and write git agents are
testable in lab mode against a GitLab-shaped double. Responses use GitLab terms
(project, path_with_namespace, merge_request, iid). Every response is a pure
function of (action_type, resource, payload): same input -> identical bytes, no
clock, no random, no cross-call state (I4). See ``_realism`` for the primitives.
"""

from __future__ import annotations

from . import _entities
from ._realism import LabActionError, derived_int, digest, envelope, ref

_DOMAIN = "gitlab"
_DISCOVERY_RESOURCES = frozenset(("", "all", "*"))


def _reject_if_archived(project: _entities.GitlabProject, action: str) -> None:
    if project.archived:
        raise LabActionError(
            422,
            f"project {project.path_with_namespace!r} is archived; cannot {action}",
            code="project_archived",
            detail={"project": project.path_with_namespace, "archived": True},
        )


_KNOWN_ACTIONS = frozenset(
    (
        "read_repo",
        "list_repos",
        "open_issue",
        "comment_issue",
        "open_pr",
        "merge_pr",
        "push",
        "manage_webhook",
    )
)


def handle(action_type: str, resource: str, payload: dict) -> dict | None:
    """Return a realistic deterministic GitLab response, or ``None`` for an
    unknown action."""
    if action_type not in _KNOWN_ACTIONS:
        return None
    dig = digest(_DOMAIN, action_type, resource, payload)
    base = envelope(action_type, resource, dig)

    if action_type == "read_repo":
        if resource in _DISCOVERY_RESOURCES:
            return {
                **base,
                "status": "ok",
                "projects_list": [
                    _entities.derive_project(p).summary() for p in _entities.SEED_PROJECTS
                ],
            }
        project = _entities.derive_project(resource)
        return {
            **base,
            "status": "ok",
            "project": {
                "path_with_namespace": project.path_with_namespace,
                "default_branch": project.default_branch,
                "visibility": project.visibility,
                "archived": project.archived,
            },
        }
    if action_type == "list_repos":
        return {
            **base,
            "status": "ok",
            "projects": [f"{resource}/{dig[:4]}-{idx}" for idx in range(3)],
        }
    if action_type == "open_issue":
        return {
            **base,
            "status": "opened",
            "issue": {"iid": derived_int(dig, 1, 10000), "state": "opened"},
        }
    if action_type == "comment_issue":
        return {**base, "status": "created", "note_id": ref("note_", dig)}
    if action_type == "open_pr":
        return {
            **base,
            "status": "opened",
            "merge_request": {"iid": derived_int(dig, 1, 10000), "state": "opened"},
        }
    if action_type == "merge_pr":
        _reject_if_archived(_entities.derive_project(resource), "merge into it")
        return {
            **base,
            "status": "merged",
            "merge_request": {"iid": derived_int(dig, 1, 10000), "merged": True},
        }
    if action_type == "push":
        _reject_if_archived(_entities.derive_project(resource), "push to it")
        return {
            **base,
            "status": "pushed",
            "branch": str(payload.get("branch") or "main"),
            "commit": dig[:12],
        }
    # manage_webhook
    return {**base, "status": "configured", "hook_id": derived_int(dig, 1, 100000)}
