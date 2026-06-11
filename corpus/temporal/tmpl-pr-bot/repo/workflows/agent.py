"""Temporal agent: dependency pull-request bot.

A Temporal workflow that reads repositories and opens a pull request per dependency
bump. Writes are bounded to opening PRs (no merge, no push to default branch).
Medium-risk subject of the discovery recette corpus (risk_rank 2).
"""

from __future__ import annotations

import os
from datetime import timedelta

from github import Github
from temporalio import activity, workflow

AGENT_PRINCIPAL = "acme-dependency-pr-bot@temporal"


def _client() -> Github:
    return Github(os.environ["GITHUB_TOKEN"])


@activity.defn
def read_repo(repo: str) -> str:
    """Read the default branch of a repository (read-only)."""
    return _client().get_repo(repo).default_branch


@activity.defn
def open_pr(repo: str, head: str, title: str) -> int:
    """Open a pull request (bounded write)."""
    r = _client().get_repo(repo)
    pr = r.create_pull(title=title, body="Automated dependency update.", head=head, base=r.default_branch)
    return pr.number


@workflow.defn
class DependencyPrBotWorkflow:
    @workflow.run
    async def run(self, repos: list[str]) -> int:
        opened = 0
        for repo in repos:
            base = await workflow.execute_activity(
                read_repo, repo, start_to_close_timeout=timedelta(seconds=30)
            )
            if not base:
                continue
            await workflow.execute_activity(
                open_pr,
                args=[repo, "deps/weekly-bump", "chore(deps): weekly dependency bump"],
                start_to_close_timeout=timedelta(seconds=60),
            )
            opened += 1
        return opened
