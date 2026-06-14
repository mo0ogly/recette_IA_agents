# Temporal discovery corpus

Test-agent subjects for the Discovery/Enrichment Plane **Temporal scanner**. Each
subject is real `temporalio` code (workflows + activities) under `repo/`; the scanner
discovers the agent by reading the workflow/activity definitions.

| Subject | Actions | risk_rank | Detected |
|---------|---------|-----------|----------|
| `tmpl-readonly-reporter` | read_repo, read_ci | 1 | yes |
| `tmpl-pr-bot` | read_repo, open_pr | 2 | yes |
| `tmpl-admin-overreach` | push, manage_webhook | 3 | yes |
| `tmpl-no-agent` | (none) | 0 | no (true negative) |

Convention: each `@activity.defn` is named after the canonical action it performs
(`read_repo`, `open_pr`, `push`, ...), and a module-level `AGENT_PRINCIPAL` string
carries the agent identity. The offline oracle (`ReferenceSourceScanAdapter`) reads
this **statically via AST** -- it never imports the modules, so the discovery recette
needs no `temporalio` install and stays deterministic (I4/I7). The `temporalio` SDK is
only required to actually run the workflows (Lane B), via the `[temporal]` extra.

Ground-truth asserts invariant properties only (detection, action coverage,
target_system, relative risk ordering, policy presence), never opaque values.

Run: `python -m recette discovery --surface temporal`
