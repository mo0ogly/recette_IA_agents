"""Dependency PR bot agent.

Scans acme repositories for outdated dependencies and opens a pull request per
bump. Writes are limited to opening PRs (no merge, no push to default branch).
Medium-risk subject of the recette corpus (risk_rank 2).
"""

from __future__ import annotations

import os

from github import Github


def build_client() -> Github:
    token = os.environ["GITHUB_TOKEN"]
    return Github(token)


def open_bump_pr(repo, branch: str, title: str, body: str) -> None:
    base = repo.default_branch  # read_repo
    repo.create_pull(title=title, body=body, head=branch, base=base)  # open_pr


def run(client: Github, org: str = "acme") -> int:
    opened = 0
    for repo in client.get_organization(org).get_repos():
        branch = "deps/weekly-bump"
        try:
            open_bump_pr(repo, branch, "chore(deps): weekly dependency bump", "Automated dependency update.")
            opened += 1
        except Exception:  # noqa: BLE001 - a missing branch just means nothing to bump
            continue
    return opened


def main() -> None:
    client = build_client()
    print(f"opened {run(client)} dependency PRs")


if __name__ == "__main__":
    main()
