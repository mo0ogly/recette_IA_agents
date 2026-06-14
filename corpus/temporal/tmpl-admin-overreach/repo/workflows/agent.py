"""Temporal agent: infrastructure syncer (high blast radius).

A Temporal workflow that pushes synchronized config files to repositories and
installs webhooks. Both are high blast-radius writes. Highest-risk subject of the
discovery recette corpus (risk_rank 3).
"""

from __future__ import annotations

import os
from datetime import timedelta

from github import Github
from temporalio import activity, workflow

AGENT_PRINCIPAL = "acme-infra-syncer@temporal"


def _client() -> Github:
    return Github(os.environ["GITHUB_TOKEN"])


@activity.defn
def push(repo: str, path: str, content: str) -> str:
    """Commit a file to the default branch (high blast-radius write)."""
    r = _client().get_repo(repo)
    existing = r.get_contents(path)
    r.update_file(path, "chore: sync infra config", content, existing.sha)
    return "pushed"


@activity.defn
def manage_webhook(repo: str, url: str) -> int:
    """Install a push webhook (high blast-radius write)."""
    r = _client().get_repo(repo)
    hook = r.create_hook("web", {"url": url, "content_type": "json"}, events=["push"], active=True)
    return hook.id


@workflow.defn
class InfraSyncWorkflow:
    @workflow.run
    async def run(self, repos: list[str], hook_url: str) -> None:
        for repo in repos:
            await workflow.execute_activity(
                push,
                args=[repo, ".inspect_ia_agents/sync.yml", "managed: true\n"],
                start_to_close_timeout=timedelta(seconds=60),
            )
            await workflow.execute_activity(
                manage_webhook,
                args=[repo, hook_url],
                start_to_close_timeout=timedelta(seconds=30),
            )
