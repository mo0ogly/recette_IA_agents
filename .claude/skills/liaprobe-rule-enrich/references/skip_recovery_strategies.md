# Skip & Recovery Strategies

When a cycle cannot apply, the pipeline records a skip (not a failure) and
keeps going. This file is the decision matrix: when to skip, what to log, and
how to recover later.

## Principle

A skip is honest. Fabricating a value to avoid a skip violates R4 (no mock)
and R18 (verify facts). A product with no documented CVE / no endoflife.date
entry / no ATT&CK mapping is correctly skipped, not invented.

## Skip decision matrix

| Cycle | Condition | Logged reason | Recovery |
|-------|-----------|---------------|----------|
| 4 CVE | no `cpe23_template` | (skip, continue 5+7) | add a CPE later via vendor sync, then re-run |
| 4 CVE | 0 CVE matched | (skip 7 too) | none -- product genuinely has no catalogued CVE |
| 5 EOL | `no slug` | no slug derivable | add a row to `endoflife_slug_mapping.csv`, re-run |
| 5 EOL | `network` | fetch failed | transient -- re-run after retry budget |
| 5 EOL | `http_{status}` | non-200 (often 404) | product not on endoflife.date; defer |
| 5 EOL | `no_data` | parsed empty | defer until upstream populates |
| 7 MITRE | `no_cves` | known_cves[] empty | run Cycle 4 first, then re-run 7 |
| 7 MITRE | `pg_down` | PG unavailable | re-run when PostgreSQL is back |
| 7 MITRE | `no_match` | 0 technique mapped | none -- no ATT&CK link for those CVEs |

## TODO_UNVERIFIED block (do not invent)

When data cannot be verified (rate limit, paywall, no public doc), do NOT
fabricate. Record it in an explicit `todo_unverified_*` block in the master
JSON so a future pass (or lab capture) can resolve it:

```json
"todo_unverified_indicators": {
  "qnap_qts_default": "Need verification: vendor doc URL paywalled. Drop until lab capture."
}
```

This is more honest than a "trust me" value and produces a concrete Phase-2
worklist.

## Recovery ordering

1. Fix the precondition (CPE, slug CSV row, PG up).
2. Re-run only the skipped cycle(s) -- idempotence skips already-enriched
   rules.
3. If 2 consecutive failures (not skips) on the same rule -> `/replan`.

## Related

- `error_handling.md` -- retry budget + replan trigger.
- `.claude/rules/liaprobe-enrich-protocol.md` -- TODO_UNVERIFIED pattern,
  per-entry source tracking, Phase 1/Phase 2 split.
