"""Release builder agent (compromised supply chain).

OWASP Agentic 2026 ASI04 (Agentic Supply Chain Compromise): the agent's build
toolchain is pulled from an UNTRUSTED package index (see .github/workflows/agent.yml),
so attacker-controlled code runs inside the build with the agent's write token and
is pushed to the default branch. The git capabilities themselves (read_repo + push)
are ordinary; the compromise is in WHERE the toolchain comes from -- a supply-chain
vector a static scanner sees in the CI surface, not in the action set.
"""

from __future__ import annotations

import os

from github import Github

# Untrusted build toolchain: installed from a non-canonical index in CI (agent.yml).
# A typosquatted / attacker-hosted "acme-buildkit" can execute arbitrary code here.
from acme_buildkit import build_release  # type: ignore[import-not-found]


def build_client() -> Github:
    token = os.environ["GITHUB_TOKEN"]
    return Github(token)


def publish_release(repo, tag: str) -> None:
    branch = repo.default_branch
    tree = repo.get_contents("", ref=branch)  # read_repo
    artifact = build_release(tree)  # runs untrusted toolchain code with the write token
    repo.update_file(  # push to default branch
        f"dist/{tag}.tar.gz", f"release: {tag}", artifact, repo.get_contents(f"dist/{tag}.tar.gz", ref=branch).sha, branch=branch
    )


def run(client: Github, org: str = "acme") -> None:
    for repo in client.get_organization(org).get_repos():
        publish_release(repo, "v1.0.0")


def main() -> None:
    run(build_client())
