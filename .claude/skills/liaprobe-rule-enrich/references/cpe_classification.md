# CPE Classification -- Trust Rules (R18 enforcement)

Used by the vendor-sync sub-mode to decide whether a rule's CPE can be
trusted to attribute a canonical vendor.

## CPE part trust table

| Part | Trust | Reason |
|------|-------|--------|
| `:a:` | YES | application = service vendor is authoritative |
| `:h:` | YES | hardware = device vendor (Bosch/Motorola/Cisco) is authoritative |
| `:o:` | NO | OS host = misattribution risk -- e.g. `cpe:2.3:o:microsoft:windows` for ANY service running on Windows |

Incident 2026-05-03: trusting `:o:` wrongly attributed 521 rules to Microsoft
because the OS CPE describes the host, not the fingerprinted service. `:o:` is
permanently excluded from vendor attribution.

## CPE 2.2 vs 2.3

The parser accepts both `cpe:/a:vendor:product` (2.2) and
`cpe:2.3:a:vendor:product:...` (2.3). Vendor + product are extracted from the
positional fields after the part marker.

## Classification contract (INVARIANT)

```
CONFIDENT  -> CPE :a: or :h: AND alias_exact match
DOUBTFUL   -> fuzzy_trgm | product_only | sub_product | no_cpe-but-product
              | banner_literal | notes_capword | id_slug | taxonomy_token
              | filename_token
SKIP       -> no_cpe AND no_match
```

Any method other than `alias_exact` -- even with a trusted `:a:`/`:h:` CPE --
MUST bucket as DOUBTFUL. There is NO auto-CONFIDENT path for `product_only_*`,
`banner_*`, `notes_*`, `id_slug_*`, `filename_*`, `taxonomy_*`. R4 + R18
enforcement: a fuzzy or heuristic match is never silently promoted to
CONFIDENT.

## Apply discipline

- `--apply` writes CONFIDENT only.
- DOUBTFUL and SKIP leave `legacy_id` / `legacy_taxonomy_code` untouched.
- CONFIDENT rewrites preserve `legacy_id` and `legacy_taxonomy_code` for
  audit.

## Related

- `vendor_sync_workflow.md` -- the 8-phase workflow that consumes this table.
- `false_positive_corpus.md` -- regression cases that prove the DOUBTFUL
  guards.
