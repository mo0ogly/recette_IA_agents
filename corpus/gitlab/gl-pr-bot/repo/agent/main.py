"""GitLab dependency merge-request bot agent.

Reads acme projects and opens a merge request per dependency bump. Bounded write
(MR creation only; no push to default branch, no merge). Risk_rank 2.
"""

from __future__ import annotations

import os

import gitlab


def build_client() -> gitlab.Gitlab:
    return gitlab.Gitlab(url=os.environ["GITLAB_URL"], private_token=os.environ["GITLAB_TOKEN"])


def open_bump_mr(project, source_branch: str, title: str) -> None:
    target = project.default_branch  # read_repo
    project.mergerequests.create(
        {"source_branch": source_branch, "target_branch": target, "title": title}  # open_pr
    )


def run(client: gitlab.Gitlab, group: str = "acme") -> int:
    opened = 0
    for project in client.groups.get(group).projects.list(iterator=True):
        full = client.projects.get(project.id)
        open_bump_mr(full, "deps/weekly-bump", "chore(deps): weekly dependency bump")
        opened += 1
    return opened


def main() -> None:
    print(f"opened {run(build_client())} merge requests")


if __name__ == "__main__":
    main()
