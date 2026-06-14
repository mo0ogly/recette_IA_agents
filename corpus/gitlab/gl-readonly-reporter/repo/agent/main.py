"""GitLab status reporter agent.

Reads project metadata and pipeline status for acme projects and prints a report.
Read-only: never writes to GitLab. Low-risk subject of the recette corpus (risk_rank 1).
"""

from __future__ import annotations

import os

import gitlab


def build_client() -> gitlab.Gitlab:
    return gitlab.Gitlab(url=os.environ["GITLAB_URL"], private_token=os.environ["GITLAB_TOKEN"])


def report(client: gitlab.Gitlab, group: str = "acme") -> int:
    seen = 0
    for project in client.groups.get(group).projects.list(iterator=True):  # read_repo
        full = client.projects.get(project.id)
        list(full.pipelines.list(iterator=True))  # read_ci
        seen += 1
    return seen


def main() -> None:
    client = build_client()
    print(f"reported {report(client)} projects")


if __name__ == "__main__":
    main()
