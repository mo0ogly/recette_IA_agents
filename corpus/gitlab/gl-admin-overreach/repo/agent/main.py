"""GitLab infrastructure syncer agent (high blast radius).

Commits config files to project default branches and installs push webhooks. Both are
high blast-radius writes. Highest-risk subject of the recette corpus (risk_rank 3).
"""

from __future__ import annotations

import os

import gitlab


def build_client() -> gitlab.Gitlab:
    return gitlab.Gitlab(url=os.environ["GITLAB_URL"], private_token=os.environ["GITLAB_TOKEN"])


def sync(client: gitlab.Gitlab, hook_url: str, group: str = "acme") -> None:
    for project in client.groups.get(group).projects.list(iterator=True):
        full = client.projects.get(project.id)
        full.files.create(  # push
            {
                "file_path": ".inspect_ia_agents/sync.yml",
                "branch": full.default_branch,
                "content": "managed: true\n",
                "commit_message": "chore: sync infra config",
            }
        )
        full.hooks.create({"url": hook_url, "push_events": True})  # manage_webhook


def main() -> None:
    sync(build_client(), os.environ["INSPECT_IA_AGENTS_HOOK_URL"])


if __name__ == "__main__":
    main()
