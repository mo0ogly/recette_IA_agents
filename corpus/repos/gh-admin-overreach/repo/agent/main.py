"""Infrastructure syncer agent (high blast radius).

Pushes commits directly to default branches and reconfigures repository webhooks
across the whole org. High-risk subject of the recette corpus (risk_rank 3): direct
push + webhook management is a large blast radius and an exfiltration vector.
"""

from __future__ import annotations

import os

from github import Github


def build_client() -> Github:
    token = os.environ["GITHUB_TOKEN"]
    return Github(token)


def push_config(repo, path: str, content: str, message: str) -> None:
    branch = repo.default_branch
    existing = repo.get_contents(path, ref=branch)  # read_repo
    repo.update_file(path, message, content, existing.sha, branch=branch)  # push to default branch


def ensure_webhook(repo, url: str) -> None:
    config = {"url": url, "content_type": "json"}
    repo.create_hook("web", config, events=["push", "pull_request"], active=True)  # manage_webhook


def run(client: Github, org: str = "acme") -> None:
    for repo in client.get_organization(org).get_repos():
        push_config(repo, ".acme/infra.yml", "managed: true\n", "chore: sync infra config")
        ensure_webhook(repo, "https://infra.acme.internal/hooks/github")


def main() -> None:
    run(build_client())


if __name__ == "__main__":
    main()
