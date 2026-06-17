"""Git lab entities: GitHub repositories and GitLab projects.

Visibility/default_branch stay literal ("private"/"main") because the read
handlers assert them; ``archived`` is the entity's behavioural state.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "SEED_ARCHIVED_PROJECTS",
    "SEED_ARCHIVED_REPOS",
    "SEED_PROJECTS",
    "SEED_REPOS",
    "GitlabProject",
    "Repository",
    "derive_project",
    "derive_repository",
]

SEED_REPOS = ("github/repo/app", "github/repo/infra")
SEED_ARCHIVED_REPOS = ("github/repo/archived-1",)
SEED_PROJECTS = ("gitlab/project/app", "gitlab/project/infra")
SEED_ARCHIVED_PROJECTS = ("gitlab/project/archived-1",)


@dataclass(frozen=True)
class Repository:
    """A GitHub repository, fully derived from its full name."""

    full_name: str
    visibility: str
    default_branch: str
    archived: bool

    def summary(self) -> dict:
        return {"full_name": self.full_name, "archived": self.archived}


def derive_repository(full_name: str) -> Repository:
    name = full_name or "github/repo/unknown"
    return Repository(
        full_name=name,
        visibility="private",
        default_branch="main",
        archived=name in SEED_ARCHIVED_REPOS,
    )


@dataclass(frozen=True)
class GitlabProject:
    """A GitLab project, fully derived from its path."""

    path_with_namespace: str
    visibility: str
    default_branch: str
    archived: bool

    def summary(self) -> dict:
        return {"path_with_namespace": self.path_with_namespace, "archived": self.archived}


def derive_project(path: str) -> GitlabProject:
    p = path or "gitlab/project/unknown"
    return GitlabProject(
        path_with_namespace=p,
        visibility="private",
        default_branch="main",
        archived=p in SEED_ARCHIVED_PROJECTS,
    )
