"""Dependency PR bot with a BROKEN passport.

Opens pull requests to bump outdated dependencies across acme repositories --
identical behaviour to the sanctioned pr-bot. The difference is the passport:
`.inspect_ia_agents/manifest.json` EXISTS but is structurally invalid (it is
missing the whole `agent.identity` object), so it parses as JSON yet fails
manifest validation. A discovery scanner must detect the agent (code fallback)
AND surface passport_status = invalid -- a broken manifest must never be
silently trusted as if it declared a valid identity/scope.
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
