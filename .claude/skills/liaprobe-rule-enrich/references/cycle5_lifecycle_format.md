# Cycle 5 -- Lifecycle (EOL) Format

Source of truth: `scripts/enrich_cycle_5_eol.py` (`_build_lifecycle`).

## Schema target -- lifecycle{}

Injected at the top level of the fingerprint JSON as `rule.lifecycle`:

```json
"lifecycle": {
  "data_source": "endoflife.date",
  "latest_cycle": "8.2",
  "released": "2024-03-11",
  "eol": "2026-03-11",
  "is_eol_now": false,
  "current_stable": "8.2.1",
  "lts_cycle": "7.0",
  "lts_eol": "2027-12-31",
  "extended_support_until": "2028-06-30",
  "support_until": "2025-09-30"
}
```

Fields (all `None`/null values are stripped before injection):
- `data_source` : always `"endoflife.date"`.
- `latest_cycle` : newest release cycle id (by `releaseDate`).
- `released` : ISO release date of the latest cycle.
- `eol` : ISO end-of-life date of the latest cycle (parsed from the API
  string/boolean/null via `_parse_eol_value`).
- `is_eol_now` : boolean -- true when the latest cycle eol is in the past or
  the API reported a boolean `true`.
- `current_stable` : `latest` field of the newest cycle, else the cycle id.
- `lts_cycle` / `lts_eol` : only present when a cycle carries `lts: true`.
- `extended_support_until` : only when the latest cycle has a string
  `extendedSupport`.
- `support_until` : only when the latest cycle has a string `support`.

## Slug resolution

`_resolve_slug(rule_data, slug_csv_path)`:
1. Lookup the rule `product_key` in
   `master_data/endoflife_slug_mapping.csv` (column `endoflife_slug`).
2. Fall back to a slugified `product` / `vendor` if no CSV row.

## API call

```
GET https://endoflife.date/api/{slug}.json
```

Cached under `<tracking-root>/runtime/endoflife_cache/` (HTTPClient cache).
No API key required.

## Skip conditions (non-fail)

- `no slug` : product/vendor cannot derive a slug -> `mark_cycle_skipped`.
- `network` : fetch returned no response.
- `http_{status}` : endoflife.date returned a non-200 (e.g. 404 for a niche
  product with no entry).
- `no_data` : response parsed but produced no usable lifecycle block.

A skip is logged and the cycle continues; it is NOT a failure.

## Limits

- One lifecycle block per signature (aggregated from the newest cycle).
- Skip products absent from endoflife.date (niche / archived software).
