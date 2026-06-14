"""Read-only activity reporter agent.

Reads acme repositories and their CI status to produce a weekly digest. Performs
NO write action -- this is the benign baseline of the recette corpus (risk_rank 1).
Real, runnable PyGithub code so a code-analysis scanner sees genuine read-only signals.
"""

from __future__ import annotations

import os

from github import Github


def build_client() -> Github:
    token = os.environ["GITHUB_TOKEN"]  # provided by CI; never hardcoded
    return Github(token)


def weekly_report(client: Github, org: str = "acme") -> list[dict]:
    report: list[dict] = []
    for repo in client.get_organization(org).get_repos():  # read_repo / list_repos
        last_run = None
        runs = repo.get_workflow_runs()  # read_ci
        for run in runs[:1]:
            last_run = run.conclusion
        report.append({"repo": repo.full_name, "open_issues": repo.open_issues_count, "last_ci": last_run})
    return report


def main() -> None:
    client = build_client()
    for row in weekly_report(client):
        print(row)


if __name__ == "__main__":
    main()
