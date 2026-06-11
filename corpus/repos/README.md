# Recette repo corpus -- realistic GitHub test-agent repositories

Each subdirectory is a **realistic, publishable GitHub repository** used as a
ground-truth test subject for the colleague's Discovery / Enrichment GitHubScanner
(`:8081`, "agent code analysis + CI/CD surface"). The scanner reads the repo content;
these are intentionally real (runnable agent code, real CI/CD, real `.agentrail`
manifest) so the scanner analyzes them *as if they were real agents*.

## Layout

```
corpus/repos/<slug>/
  repo/                          # the publishable repository tree (what the scanner reads)
    .agentrail/manifest.json     # ManifestScanner native surface (highest precision) -- omitted for true negatives
    .github/workflows/*.yml      # CI/CD surface
    agent/main.py                # genuine runnable agent code (the action-pattern source)
    README.md
  discovery-ground-truth.json    # what the scanner MUST conclude (schema: discovery-ground-truth.schema.json)
```

## Realism

Realism = *static* realism: the repo content is genuine and runnable, but the recette
does NOT execute the agents against live GitHub (no side effects, deterministic). The
GitHubScanner does code + CI analysis, so static realistic content is sufficient and
keeps the recette reproducible. Live execution (real PRs/commits) is an out-of-scope
optional extension (RealForge).

## Ground-truth is invariant-based, not value-based

`canonical_agent_id` and `estimated_risk` are computed internally by the scanner and are
opaque (arch invariant 2 + fingerprinting). Ground-truth therefore asserts invariant
properties: detection, agent count, action-pattern coverage, target_system, **relative**
risk ordering (`risk_rank`), and policy presence -- never exact opaque values.

## Corpus set

| slug | risk_rank | surface | role |
|------|-----------|---------|------|
| `gh-readonly-reporter` | 1 | read_repo, read_ci | benign baseline |
| `gh-pr-bot` | 2 | read_repo, open_pr | medium (bounded write) |
| `gh-admin-overreach` | 3 | read_repo, push, manage_webhook | high blast radius |
| `gh-no-agent` | 0 | none | TRUE NEGATIVE (no agent) |

The recette checks the scanner ranks `gh-readonly-reporter < gh-pr-bot < gh-admin-overreach`
and reports nothing for `gh-no-agent`.

## Publishing

`python -m recette publish <slug> --owner <org>` turns a `repo/` tree into a real GitHub
repo (dry-run by default; `--apply` to create). See `docs/runbooks/github-discovery-recette.md`.
