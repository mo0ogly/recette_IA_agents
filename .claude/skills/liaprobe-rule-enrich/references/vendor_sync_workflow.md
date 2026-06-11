# Vendor Sync Workflow

Sub-mode of the enrich skill. Distinct from enrichment: ENRICHMENT injects
metadata (`known_cves`, `lifecycle`, `attack_surface`); VENDOR SYNC remaps
identifiers. It synchronises each LiaProbe rule with PostgreSQL `vendor` +
`vendor_alias` to produce a canonical `lia_signature_key` (e.g.
`lia_v2716_p4521`) and replaces legacy `id` / `taxonomy_code` with
`vendor_product` forms, preserving `legacy_id` / `legacy_taxonomy_code` for
audit.

## 8-phase workflow

```
A1 SETUP    : pg_trgm extension + product indexes (lower_name, GIN trgm) verified
A2 AUDIT    : dry-run categorize all rules -> v_baseline.csv (CONFIDENT/DOUBTFUL/SKIP distribution)
A3 PHASE_A  : CPE :a: + :h: trust + CPE 2.2 parser; skip :o: -> v_phaseA.csv
A4 PHASE_B  : product_only fallback (no CPE -> rule.product ILIKE product table), bucket=DOUBTFUL -> v_phaseB.csv
A5 BRAIN    : 6-agent brainstorm Phase C strategies IF SKIP > 50% (5 strategists + 1 adversarial mandatory)
A6 WAVES    : C1 -> C2 -> C3 sequential; regression sample 20 random DOUBTFUL/wave; FP > 10% -> ROLLBACK
A7 APPLY    : --apply CONFIDENT only (preserve legacy_id, legacy_taxonomy_code); DOUBTFUL/SKIP untouched
A8 COMMIT   : RETEX + CSV + INDEX update + tests green
```

## Pre-flight gates (BLOCKING before A2)

- [ ] `pg_trgm` extension exists.
- [ ] `product` table has `idx_product_lower_name` (btree).
- [ ] `product` table has `idx_product_name_trgm` (GIN).
- [ ] `vendor_alias` table has `idx_vendor_alias_lower_unique`.
- [ ] `vendor_alias` table has `idx_vendor_alias_trgm` (GIN).
- [ ] Migration `NNN_product_name_indexes.sql` applied
      (template `migrations/147_product_name_indexes.sql`).
- [ ] Backup before any bulk seed > 100 rows:
      `pg_dump -t vendor_alias -t vendor` to `/opt/lia-sec/backups/vendor_alias/`.

## Resolver classification contract

See `cpe_classification.md`. Summary: CONFIDENT requires CPE `:a:`/`:h:` AND
`alias_exact`; every heuristic method buckets DOUBTFUL; no-CPE-and-no-match is
SKIP. No auto-CONFIDENT for any fuzzy/heuristic method.

## Phase C strategies + adversarial guards

| # | Strategy | Bucket | Required guard |
|---|----------|--------|----------------|
| 1 | id slug parser | DOUBTFUL | tcp-probes only, proto blacklist, alias_exact |
| 2 | filename parser | DOUBTFUL | Method A only, generic stoplist, alias_exact |
| 3 | banner regex literal | DOUBTFUL | conf >= 0.80, supplementary only, NEVER primary |
| 4 | notes/tags capword | DOUBTFUL | STOPWORDS + GENERIC_TAGS denylist, alias_exact, conf >= 0.85 |
| 5 | taxonomy first-token | DOUBTFUL | exact match only, blacklist THE/EASY/ABLE/GRAPHQL/GENERIC/UNKNOWN/MISC |
| 6 | adversarial auditor | N/A | mandatory before merge of strategies 1-5 |

## Phase D strategies (post-Phase-C)

| # | Strategy | Verdict |
|---|----------|---------|
| D1 | website domain root | NO-GO standalone (4.4% yield, 25-30% FP) -> manual curation |
| D2 | taxonomy_name first capword | DOUBTFUL, alias_exact + extended noise-token denylist; solo verify 20/20 TP |
| D3 | taxonomy_name bigram | not implemented (low yield) |
| D4 | implies array | NO-GO standalone (notes_capword-class runtime trap) |

## Wave protocol

Between waves: full dry-run on the whole corpus, sample 20 random DOUBTFUL
from the new method, manually verify FP rate, ROLLBACK if FP > 10%. Document
each sample verification under `recettes/.../wave_CN_sample_verify.md`.

## Related

- `cpe_classification.md` -- CPE trust table + classification contract.
- `false_positive_corpus.md` -- mandatory regression cases per new method.
- `.claude/rules/liaprobe-enrich-protocol.md` -- pre-flight checks, brainstorm
  protocol, vendor alias scoring sub-mode, session layout.
