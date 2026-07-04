"""Shadow dependency PR bot (NO passport in this tree).

Opens pull requests to bump outdated dependencies across acme repositories,
exactly like the sanctioned pr-bot -- but this tree carries NO
.inspect_ia_agents/ passport directory anywhere. It is the shadow-agent
subject of the recette corpus: real-looking agent code importing the github
SDK with no declared identity, capabilities, or policy. A discovery scanner
must detect the agent from the code AND surface the missing passport
(passport_status = absent), never silently ignore an undeclared agent.
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
