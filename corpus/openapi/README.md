# OpenAPI discovery corpus

Test-agent subjects for the Discovery/Enrichment Plane **OpenAPI scanner**. Each subject
is a real OpenAPI 3.1 document at `repo/openapi.json`; the scanner discovers the agent by
reading the spec's operations.

| Subject | Actions | risk_rank | Detected |
|---------|---------|-----------|----------|
| `oas-readonly-reporter` | read_repo, read_ci | 1 | yes |
| `oas-pr-bot` | read_repo, open_pr | 2 | yes |
| `oas-admin-overreach` | push, manage_webhook | 3 | yes |
| `oas-no-agent` | (none) | 0 | no (true negative) |

Convention: each operation declares its capability via `operationId` (or an
`x-agentrail-action` extension) set to a canonical action, and `info.x-agentrail-principal`
carries the agent identity. The offline oracle parses the JSON statically (stdlib `json`,
deterministic, zero extra dependency).

Ground-truth asserts invariant properties only (detection, action coverage, target_system,
relative risk ordering, policy presence), never opaque values.

Run: `python -m recette discovery --surface openapi`
