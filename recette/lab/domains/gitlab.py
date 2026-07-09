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
from ._realism import LabActionError, derived_int, digest, envelope, pick, ref

_DOMAIN = "gitlab"
_DISCOVERY_RESOURCES = frozenset(("", "all", "*"))

#: Triage labels a GitLab-shaped tracker would carry (picked per input).
_ISSUE_LABELS = ("bug", "feature", "documentation", "security", "backstage")


def _web_url(path: str) -> str:
    """Simulated project web URL (lab host, never a real GitLab instance)."""
    return f"https://gitlab.example.test/{path or 'gitlab/project/unknown'}"


def _author(dig: str) -> str:
    """A stable simulated author username derived from the input digest."""
    return f"usr_{dig[20:28]}"


def _text(raw: object, fallback: str) -> str:
    """A trimmed string field: the payload value when present, else the
    deterministic fallback."""
    text = str(raw).strip() if isinstance(raw, str) else ""
    return text or fallback


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
                "star_count": derived_int(dig, 0, 120),
                "open_issues_count": derived_int(dig, 0, 60, offset=4),
                "web_url": _web_url(project.path_with_namespace),
            },
        }
    if action_type == "list_repos":
        return {
            **base,
            "status": "ok",
            "projects": [f"{resource}/{dig[:4]}-{idx}" for idx in range(3)],
        }
    if action_type == "open_issue":
        iid = derived_int(dig, 1, 10000)
        return {
            **base,
            "status": "opened",
            "issue": {
                "iid": iid,
                "state": "opened",
                "title": _text(payload.get("title"), f"issue {dig[:6]}"),
                "author": _author(dig),
                "labels": [pick(dig, _ISSUE_LABELS, offset=8)],
                "confidential": bool(payload.get("confidential", False)),
                "web_url": f"{_web_url(resource)}/-/issues/{iid}",
            },
        }
    if action_type == "comment_issue":
        return {
            **base,
            "status": "created",
            "note_id": ref("note_", dig),
            "noteable_iid": derived_int(dig, 1, 10000, offset=4),
            "author": _author(dig),
            "body_preview": _text(payload.get("body"), "")[:80],
        }
    if action_type == "open_pr":
        project = _entities.derive_project(resource)
        iid = derived_int(dig, 1, 10000)
        return {
            **base,
            "status": "opened",
            "merge_request": {
                "iid": iid,
                "state": "opened",
                "title": _text(payload.get("title"), f"merge request {dig[:6]}"),
                "source_branch": _text(payload.get("branch"), f"feature/{dig[:6]}"),
                "target_branch": project.default_branch,
                "draft": bool(payload.get("draft", False)),
                "changes_count": derived_int(dig, 1, 40, offset=8),
                "web_url": f"{_web_url(resource)}/-/merge_requests/{iid}",
            },
        }
    if action_type == "merge_pr":
        _reject_if_archived(_entities.derive_project(resource), "merge into it")
        return {
            **base,
            "status": "merged",
            "merge_request": {
                "iid": derived_int(dig, 1, 10000),
                "merged": True,
                "merge_commit_sha": dig[:40],
                "merged_by": _author(dig),
                "squash": bool(payload.get("squash", False)),
            },
        }
    if action_type == "push":
        project = _entities.derive_project(resource)
        _reject_if_archived(project, "push to it")
        branch = str(payload.get("branch") or "main")
        return {
            **base,
            "status": "pushed",
            "branch": branch,
            "commit": dig[:12],
            "commit_sha": dig[:40],
            "commits_count": derived_int(dig, 1, 6, offset=4),
            "protected_branch": branch == project.default_branch,
            "forced": bool(payload.get("force", False)),
        }
    # manage_webhook
    return {
        **base,
        "status": "configured",
        "hook_id": derived_int(dig, 1, 100000),
        "url": _text(payload.get("url"), f"https://hooks.example.test/gl/{dig[:10]}"),
        "events": list(payload.get("events") or ("push_events", "merge_requests_events")),
    }
