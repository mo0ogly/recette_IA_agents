# GitLab discovery corpus

Test-agent subjects for GitLab discovery parity (the repo/CI surface, `target_system =
gitlab`). Each subject declares identity + capabilities in `repo/.agentrail/manifest.json`
and ships realistic `python-gitlab` agent code + `.gitlab-ci.yml` for realism.

| Subject | Actions | risk_rank | Detected |
|---------|---------|-----------|----------|
| `gl-readonly-reporter` | read_repo, read_ci | 1 | yes |
| `gl-pr-bot` | read_repo, open_pr (merge request) | 2 | yes |
| `gl-admin-overreach` | push, manage_webhook | 3 | yes |
| `gl-no-agent` | (none) | 0 | no (true negative) |

The oracle resolves these from the manifest (the precedence shared by every surface), so
`target_system = gitlab` flows from the declaration. Ground-truth asserts invariant
properties only. Run: `python -m recette discovery --surface gitlab`
