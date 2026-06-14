"""Temporal agent: scheduled repository status reporter.

A Temporal workflow that periodically reads repository and CI state for a set of
repositories and emits a status report. Read-only -- it never writes back to the
target system. Low-risk subject of the discovery recette corpus (risk_rank 1).

Each @activity.defn is named after the canonical action it performs, which is the
signal a Temporal scanner uses to map the agent's capabilities.
"""

from __future__ import annotations

import os
from datetime import timedelta

from github import Github
from temporalio import activity, workflow

AGENT_PRINCIPAL = "acme-status-reporter@temporal"


def _client() -> Github:
    return Github(os.environ["GITHUB_TOKEN"])


@activity.defn
def read_repo(repo: str) -> dict:
    """Read repository metadata (read-only)."""
    r = _client().get_repo(repo)
    return {"default_branch": r.default_branch, "private": r.private}


@activity.defn
def read_ci(repo: str) -> dict:
    """Read the latest CI/CD run status (read-only)."""
    runs = _client().get_repo(repo).get_workflow_runs()
    latest = next(iter(runs), None)
    return {"status": latest.status if latest else "none"}


@workflow.defn
class StatusReporterWorkflow:
    @workflow.run
    async def run(self, repos: list[str]) -> list[dict]:
        report: list[dict] = []
        for repo in repos:
            meta = await workflow.execute_activity(
                read_repo, repo, start_to_close_timeout=timedelta(seconds=30)
            )
            ci = await workflow.execute_activity(
                read_ci, repo, start_to_close_timeout=timedelta(seconds=30)
            )
            report.append({"repo": repo, "meta": meta, "ci": ci})
        return report
