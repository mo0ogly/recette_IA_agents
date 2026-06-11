# Error Handling -- Retry, Skip, Replan

Governs how the enrich pipeline reacts to failures. Two distinct outcomes:
recoverable error (retry) vs ambiguous-but-not-failure (skip + log).

## Retry policy

| Failure | Action |
|---------|--------|
| API timeout (endoflife.date) | 1 retry, backoff 2s |
| PG connection refused | 1 retry, then log + skip the dependent cycle |
| 2 consecutive failures on a rule | STOP -> invoke `/replan`, do NOT improvise an untraced fallback |

`/replan` produces `PLAN_RULE_ENRICH_{ruleId}_REPLAN_*.md` with an adjusted
plan. Never silently swap to an alternate path.

## Skip (non-fail) vs Fail

A skip is a logged, expected outcome -- the cycle could not apply but the run
continues. A fail is an unrecoverable error that, after the retry budget,
triggers replan.

### Per-cycle skip reasons (logged via `mark_cycle_skipped`)

- Cycle 4 (CVE): no `cpe23_template` -> skip CVE, continue 5 and 7.
- Cycle 5 (EOL): `no slug` | `network` | `http_{status}` | `no_data`
  (see `cycle5_lifecycle_format.md`).
- Cycle 7 (MITRE): `no_cves` (run cycle 4 first) | `pg_down` | `no_match`
  (see `cycle7_mitre_format.md`).

A skip never restores from `.bak`; it leaves the rule as-is and records the
reason in the state file.

## Dependency ordering

- Cycle 7 depends on Cycle 4 (`known_cves[]`). If Cycle 4 skipped/empty,
  Cycle 7 skips with `no_cves`.
- Cycles 5 and 7 both depend on a valid input + backup (steps 1-2).

## Idempotence

Rules already flagged with a rich `_meta_enrichment` are auto-skipped by
`enrich_lib` -- re-running the batch is safe and does not duplicate content.

## VERIFICATION GATE failure

If the post-run gate fails (schema broken, regex mutated, no section
injected, transformative gain too low): STOP, restore `.bak`, fix, re-run.
Never ship a rule whose existing detection regex changed.

## Related

- `skip_recovery_strategies.md` -- the skip decision matrix.
- `cycle4_cve_format.md`, `cycle5_lifecycle_format.md`,
  `cycle7_mitre_format.md` -- per-cycle schema + skip conditions.
- `.claude/rules/liaprobe-enrich-protocol.md` -- pre-flight gates + brainstorm
  + wave protocol.
