"""GitLab release builder agent (compromised supply chain).

OWASP Agentic 2026 ASI04 (Agentic Supply Chain Compromise): the agent's build
toolchain is pulled from an UNTRUSTED package index (see .gitlab-ci.yml), so
attacker-controlled code runs inside the CI job with the agent's write token and
is pushed to the default branch. The git capabilities themselves (read_repo +
push) are ordinary; the compromise is in WHERE the toolchain comes from -- a
supply-chain vector a static scanner sees in the CI surface, not in the action set.
"""

from __future__ import annotations

import os

import gitlab

# Untrusted build toolchain: installed from a non-canonical index in CI
# (.gitlab-ci.yml). A typosquatted / attacker-hosted "acme-buildkit" can execute
# arbitrary code here, inside the job that holds the write token below.
from acme_buildkit import build_release  # type: ignore[import-not-found]


def build_client() -> gitlab.Gitlab:
    return gitlab.Gitlab(url=os.environ["GITLAB_URL"], private_token=os.environ["GITLAB_TOKEN"])


def publish_release(project, tag: str) -> None:
    branch = project.default_branch
    tree = project.repository_tree(ref=branch)  # read_repo
    artifact = build_release(tree)  # runs untrusted toolchain code with the write token
    project.files.create(  # push to default branch
        {
            "file_path": f"dist/{tag}.tar.gz",
            "branch": branch,
            "content": artifact,
            "commit_message": f"release: {tag}",
        }
    )


def run(client: gitlab.Gitlab, group: str = "acme") -> None:
    for project in client.groups.get(group).projects.list(iterator=True):
        full = client.projects.get(project.id)
        publish_release(full, "v1.0.0")


def main() -> None:
    run(build_client())


if __name__ == "__main__":
    main()
