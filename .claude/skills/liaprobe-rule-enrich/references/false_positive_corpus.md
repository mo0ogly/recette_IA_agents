# False-Positive Regression Corpus

Confirmed false-positive cases. Any new resolver method (vendor-sync Phase C/D
strategy, or any heuristic attribution) MUST add tests asserting these do NOT
resolve to the wrong vendor before the method can merge.

## Confirmed FP cases

| Fixture | Real vendor | Trap | Must NOT resolve to |
|---------|-------------|------|---------------------|
| `CHKMK.json` | tribe29 | "Apache" appears in `notes` | Apache |
| `BAMBO.json` | Atlassian | "Tomcat" appears in `notes` | Tomcat |
| `LIA_PRINTER_NETSARANG_XLPD.json` | NetSarang | "hp LaserJet" in `banner` | HP |
| `FTPD.json` | (filename FTPD) | generic protocol name as filename | any vendor |
| taxonomy first-token | -- | tokens `THE` / `EASY` / `ABLE` / `GRAPHQL` | any vendor |

## Why each is a trap

- notes/banner mention a DIFFERENT product the target integrates with or
  proxies (CHKMK monitors Apache; BAMBO embeds Tomcat; the NetSarang LPD
  banner echoes an HP printer string). A literal substring match on
  notes/banner attributes the wrong vendor.
- generic protocol filenames (FTPD, SSHD, ...) are not vendor names.
- generic taxonomy first-tokens are English stopwords, not vendors.

## Guard requirements per strategy

- Strategy 3 (banner regex literal): conf >= 0.80, supplementary only, NEVER
  primary.
- Strategy 4 (notes/tags capword): STOPWORDS + GENERIC_TAGS denylist,
  alias_exact, conf >= 0.85.
- Strategy 5 (taxonomy first-token): exact match only; blacklist
  THE/EASY/ABLE/GRAPHQL/GENERIC/UNKNOWN/MISC.
- Strategy 1 (id slug): tcp-probes only, protocol blacklist, alias_exact.
- Strategy 2 (filename): Method A only (no ILIKE B/C), generic stoplist,
  alias_exact.

## Sampling gate (between waves)

Sample 20 random DOUBTFUL from each new method, manually verify. If FP > 10%
-> ROLLBACK the wave and tighten guards. Every new method runs the adversarial
auditor (6th brainstorm agent) before merge.

## Related

- `cpe_classification.md` -- the CONFIDENT/DOUBTFUL/SKIP contract these guards
  enforce.
- `vendor_sync_workflow.md` -- Phase C/D strategies + adversarial guard table.
- `.claude/rules/liaprobe-enrich-protocol.md` -- regression test corpus
  (mandatory before any new resolver method).
