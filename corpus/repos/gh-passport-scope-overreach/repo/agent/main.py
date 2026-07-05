"""Dependency push bot agent (scope-overreach-passport recette subject).

Reads acme repositories and pushes branch updates while bumping dependencies.
Declared capabilities (manifest): read_repo + push. Medium-high risk subject of
the recette corpus (risk_rank 3). The attestation defect lives in
.inspect_ia_agents/passport.json: its signed scope is only read_repo, so push is
performed beyond the passport scope. That gap is exercised by verify-with-declared
(declared = manifest actions), not by this code.
"""

from __future__ import annotations

import os

from github import Github


def build_client() -> Github:
    token = os.environ["GITHUB_TOKEN"]
    return Github(token)


def push_bump(repo, branch: str, path: str, message: str, content: str) -> None:
    base = repo.default_branch  # read_repo
    ref = repo.get_git_ref(f"heads/{base}")  # read_repo
    existing = repo.get_contents(path, ref=base)  # read_repo
    repo.update_file(path, message, content, existing.sha, branch=branch)  # push


def run(client: Github, org: str = "acme") -> int:
    pushed = 0
    for repo in client.get_organization(org).get_repos():
        branch = "deps/weekly-bump"
        try:
            push_bump(repo, branch, "requirements.txt", "chore(deps): weekly bump", "updated pins\n")
            pushed += 1
        except Exception:  # noqa: BLE001 - a missing file just means nothing to bump
            continue
    return pushed


def main() -> None:
    client = build_client()
    print(f"pushed {run(client)} dependency bumps")


if __name__ == "__main__":
    main()
