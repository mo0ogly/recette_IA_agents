"""Issue auto-closer agent (shadow subject: NO passport in this tree).

Closes stale issues across acme repositories. This fixture exercises the
shadow-agent detection path: real-looking agent code importing the github
SDK, with no .inspect_ia_agents/ passport directory anywhere in the tree.
"""

from __future__ import annotations

import os

from github import Github


def build_client() -> Github:
    token = os.environ["GITHUB_TOKEN"]
    return Github(token)


def close_stale_issues(client: Github, org: str = "acme") -> int:
    closed = 0
    for repo in client.get_organization(org).get_repos():
        for issue in repo.get_issues(state="open"):
            if "stale" in {label.name for label in issue.labels}:
                issue.edit(state="closed")
                closed += 1
    return closed


def main() -> None:
    client = build_client()
    print(f"closed {close_stale_issues(client)} stale issues")


if __name__ == "__main__":
    main()
