---
name: enrich-placeholder-orphan
description: Enrich placeholder orphan vendor_aliases (lia-declined / lia-meta / Unknown-O) by web-researching NVD-active vendors only. Filters orphans through CVE count > 0 to skip dead vendors. Produces idempotent migration files cmd/sigma_web/migrations/NNN_*.sql + per-orphan evidence block. Triggers on "/enrich-placeholder-orphan", "enrichis les orphelins", "resolve placeholder aliases", "review lia-declined orphans".
---

# /enrich-placeholder-orphan -- NVD-active orphan resolution loop

## Why

c38 RETEX (2026-05-13) closed the cycle marathon c24-c38 with 135 truly-unresolvable orphans on `vendor_id = 202726 (lia-declined)` after exhausting:

- pg_trgm similarity (0/10 validated on spot-check)
- 4-strategy multi-lookup (cleaned_lookup + word_first_or_last + token_substring + multi)

The remaining orphans require **per-alias web research**. Manual scope estimate: 5-10 min/orphan x 135 = 15-30 h total. NOT viable as a single batch.

This skill cuts the scope by filtering through **NVD CVE count > 0** -- a vendor with zero CVEs in `cve_nvd_data` is a dead vendor that does not deserve research time. Expected reduction: 50-70% of remaining orphans, leaving 40-70 NVD-relevant candidates for batched review.

## Position relative to other skills

- **/liaprobe-fingerprint-rebuild** scope = author engine patterns from independent observation. Produces aliases as a side effect of pattern naming.
- **/liaprobe-rule-enrich** scope = enrich an existing engine rule with CVE+MITRE metadata.
- **enrich-placeholder-orphan** scope = the *opposite direction* -- resolve already-emitted alias strings to canonical vendor_id. Pure DB-side, no pattern file change.

Composes with **/konrad-kurze** when 3 successive aliases fail the same resolution strategy.

## Constraints

- **R4** -- no mock vendor names. Every reassignment cites a verifiable source URL.
- **R5** -- migration goes in `cmd/sigma_web/migrations/NNN_*.sql`, idempotent (`WHERE vendor_id = (SELECT vendor_id FROM vendor WHERE LOWER(vendor_name)='lia-declined')`).
- **R8** -- comment block in SQL = English.
- **R13** -- never reference Wappalyzer/Nuclei/Recog when citing the alias provenance. Cite vendor doc URL only.
- **R18** -- never deduce a vendor mapping from the alias string alone. Verify via WebFetch + NVD CPE check.
- **R10** -- no emoji.

## Inputs

| Input | Source |
|-------|--------|
| Placeholder vendors | `vendor` rows where `vendor_name IN ('lia-declined','lia-meta','Unknown-O')` |
| Orphan aliases | `vendor_alias` rows where `vendor_id` matches a placeholder AND no real vendor name matches the alias |
| NVD activity | `cve_nvd_data` joined on `vendor_name` to compute CVE count per candidate target |
| Vendor docs | WebFetch on official vendor page (cited in commit + evidence block) |

## Loop (agentic)

```
INIT          -> resolve placeholder ids, count current orphans
FILTER        -> for each orphan alias, decide:
                 a) clear vendor token in alias -> propose candidate target
                 b) no candidate -> SKIP_NONCANDIDATE
RANK BY CVE   -> for each candidate target, COUNT(*) FROM cve_nvd_data WHERE vendor=$1
                 if 0 -> DEFER_DEAD_VENDOR (queued for human review later)
                 if >0 -> PROCEED
RESEARCH      -> WebFetch official vendor doc page (1 page max, content cached
                 with sha256 in evidence block)
VALIDATE      -> human checkpoint (display proposal + URL + CVE count + decision
                 boxes ACCEPT / REJECT / DEFER)
COMMIT        -> append UPDATE to in-progress migration file
                 + append evidence block to _alire/tracking/enrich-placeholder-orphan/EVIDENCE_{DATE}.md
LOOP / DONE   -> next orphan or close session
RECETTE       -> verify_engine_delta.sh (must be PRE = POST since vendor_alias
                 changes do not feed the engine matcher)
COMPLETE      -> apply migration, INDEX.md update, RETEX displayed
```

## Files produced

| File | Purpose |
|------|---------|
| `cmd/sigma_web/migrations/NNN_vendor_alias_enrich_orphan_round{R}.sql` | Reassignment UPDATEs, idempotent, ends with DO $$ assertion on expected row count |
| `_alire/tracking/enrich-placeholder-orphan/EVIDENCE_{DATE}.md` | Per-alias: vendor URL, sha256 of page, CVE count, decision rationale |
| `_alire/tracking/enrich-placeholder-orphan/DEFERRED_{DATE}.json` | Orphans skipped because CVE count = 0 (review later if NVD adds entries) |
| `_alire/02_LOGS/Journals/retex/RETEX_ENRICH_PLACEHOLDER_ORPHAN_{DATE}.md` | Session RETEX |

## PIVOT decision pattern (MANDATORY NVD pre-flight)

Every "ACCEPT or REJECT" decision on a placeholder orphan MUST be preceded by
an NVD activity check on BOTH the named candidate target AND any near-token
alternative semantically present in the alias name.

### Why this is MANDATORY

c40 incident (2026-05-13, RETEX c40 S2 A51): the c39 queue tagged
`sork-passwd-h3 -> Passwd` as "questionable, manual review". A naive
binary ACCEPT/REJECT review would have produced one of two wrong outcomes:

- ACCEPT -> reassigns to a dead vendor (Passwd: 1 CVE, 1 product)
- REJECT -> leaves the alias permanent_doubtful when a 100% correct
  canonical exists (Horde: 114 CVE)

c40 P0 NVD activity check revealed:
- Passwd (vid=370): 1 CVE / 1 product = dead
- Horde (vid=497): 114 CVE = active
- SORK = Single sign-on Reactor Kit of Horde Framework
- h3 = Horde 3 component
- "passwd" in the alias = Unix passwd backend type, NOT a vendor name

Result: mig 165 PIVOT reassign to Horde (the semantic owner), not Passwd
(the surface token). This is the canonical pattern: when the literal alias
token suggests vendor X and X is dead in NVD, look for the semantic owner Y
of the project/protocol and check Y in NVD.

### Decision tree

```
For each orphan alias `A`:

  1. Extract tokens from A: tokens = split_on_seps(A.lower())
  2. For each token t in tokens:
       cves_t = SELECT COUNT(DISTINCT cve.id) FROM cve_product cp
                JOIN product p ON ...
                JOIN vendor v ON ...
                WHERE LOWER(v.vendor_name) ILIKE '%t%'
       Record cves_t per token.
  3. Find the project/protocol "semantic owner" if A contains a known
     framework component (SORK -> Horde, qmail-toaster -> Qmail, etc.).
     Add the semantic owner as a candidate even if not a literal token.
  4. RANK candidates by cves DESC.
  5. Apply filter:
       - If top candidate cves >= 10  -> PROPOSE_MIG to top candidate
       - If top candidate cves in [1,9] -> WEBFETCH verify before mig
       - If top candidate cves == 0   -> DEFER_DEAD_VENDOR
       - If no candidate at all       -> SKIP_NONCANDIDATE
  6. NEVER reassign to a vendor with 0 CVE without a WebFetch evidence
     block proving the vendor actually exists and is canonical for the
     product family.
```

### SQL helper for the pre-flight

```sql
SELECT v.vendor_id, v.vendor_name,
       COUNT(DISTINCT cp.cve_id) AS cves,
       COUNT(DISTINCT p.product_id) AS prods
FROM vendor v
LEFT JOIN product p ON p.vendor_id = v.vendor_id
LEFT JOIN cve_product cp ON cp.product_id = p.product_id
WHERE LOWER(v.vendor_name) ILIKE :candidate_pattern
GROUP BY v.vendor_id, v.vendor_name
ORDER BY cves DESC LIMIT 5;
```

Run this for BOTH the candidate AND each plausible semantic owner alternative.

### Mandatory URL citation for semantic-owner PROPOSE (c43+ doctrine)

Every PROPOSE candidate produced via "semantic owner reasoning" (token
suggests vendor A, candidate is vendor B because A is a subproject of B,
or A was acquired by B) MUST cite a specific URL in the EVIDENCE block.
Plausible-sounding lineage chains are NOT evidence.

Required EVIDENCE format for semantic-owner PROPOSE:

```
| # | Alias | NVD-active candidate | Manual verdict | Source URL | Confidence |
|---|-------|---------------------|----------------|-----------|------------|
| N | <alias> | <vendor> (vid) | PROPOSE | <https://...> | high|medium|low |
```

Acceptable URL sources (in decreasing trust order):
1. Vendor official documentation (vendor.com/docs/product)
2. Wikipedia article that explicitly names the alias as a product/component
3. CVE advisory referencing the alias under the canonical vendor
4. Project README on the canonical vendor's GitHub org

NON-acceptable as URL source:
- "AT&T acquired Lucent which spun off Avaya, therefore any AT&T VOIP
  product = Avaya". No.
- "X sounds like a Y product". No.
- An unrelated company with the same name. No.

If no URL substantiates the link, the verdict MUST be DEFER + tag the
alias `permanent_doubtful_unverified`. Logged via apex_log_decision with
`--confidence low` for retro audit.

Incident reference: c41 batch v2 proposed `at&t starpoint -> Avaya`
without URL citation. c42 A59 WebFetch verification rejected it. The
filter is now mandatory.

### When to override the filter (rare)

The NVD-active filter MAY be overridden when:

- The orphan alias is part of an air-gapped / industrial protocol where
  NVD coverage is known to be incomplete (PLC firmware, niche ICS vendors).
  Override requires explicit WebFetch evidence block citing the vendor's
  official site + a manual `confidence: low` flag in the migration source
  comment.
- The orphan alias is itself a placeholder for a fragment (e.g.
  `unknown-snmp-agent-vendor`) and the override is to FOLD multiple
  fragments under one canonical vendor explicitly tagged `lia-aggregated`.

In ALL override cases, log the decision via `apex_log_decision` with
`--confidence low` so future RETEX can audit the override quality.

## Pre-flight (BLOCKING)

1. `psql_lia` connectivity OK.
2. Placeholder vendor ids resolved (lia-declined = 202726 + lia-meta = 202688 + Unknown-O = 73282 at c39).
3. Migration slot NNN free (check `ls cmd/sigma_web/migrations/ | tail -3`).
4. Engine baseline captured via `verify_engine_delta.sh --baseline-only` (must run AGAIN post-cycle for the delta gate).

## Status

**c39 scaffold (2026-05-13)**: directory + SKILL.md + workflow.md only.
Implementation deferred. Initial run target c40+ on the 135 NONE-tier
orphans surfaced by c38 `recover_lia_declined_aliases.py`.

## Canonical filter (c45 A71)

Use `scripts/enrich_orphan_v4_filter.py` for ALL filter decisions inside this
skill. Replaces the ad-hoc Python pasted into each cycle (c40-c44).

### CLI

```bash
# Single (alias, candidate) verdict
python3 scripts/enrich_orphan_v4_filter.py --alias "sork-vacation-h3" --candidate "Horde"

# Batch JSON [{alias, candidate}, ...]
python3 scripts/enrich_orphan_v4_filter.py --batch path/to/batch.json --json-out

# Regression guard (c43 LOW-tier 47 baseline)
python3 scripts/enrich_orphan_v4_filter.py --self-test
# Expected: 0 PASS / 29 NO_MATCH / 17 SUBSTRING_FP / 1 STOPWORD_FP
```

### Verdicts

| Verdict | Action |
|---------|--------|
| `PASS` | candidate is plausible semantic owner -> PROPOSE pending A62 URL evidence |
| `SUBSTRING_FP` | word-boundary match but semantic alignment too low OR all weak-token -> DEFER |
| `STOPWORD_FP` | all alias tokens are stop-words -> DEFER (no decision possible) |
| `NO_MATCH` | no alias token matches candidate -> DEFER |

### Filter calibration

- **v3 stop-words (13)**: corporate suffixes (inc, ltd, corp, gmbh, etc.)
- **v4 stop-words (+8)**: generic descriptors (deutsche, international, global, systems, technology, networks, software, solutions)
- **v5 WEAK_TOKENS (14)**: category words that demote PASS -> SUBSTRING_FP when matched_set fully subset (corporation, electronics, laboratories, plugin, vacation, etc.)

Calibrated against c43 LOW-tier 47 baseline. Self-test is the regression guard
for future filter changes -- any STOP_WORDS_V4 / WEAK_TOKENS / MIN_SEMANTIC_OVERLAP
edit MUST keep the c43 baseline output (zero PASS).

### Refresh RECOVERY snapshot

c45 A70 added `scripts/refresh_recovery_candidates.py` which regenerates the
RECOVERY_CANDIDATES snapshot against current `vendor_alias` state using the
v4+v5 filter for tier classification.

```bash
python3 scripts/refresh_recovery_candidates.py \
    --out _alire/tracking/liaprobe-fingerprint-rebuild/RECOVERY_CANDIDATES_$(date +%Y-%m-%d).json
```

Use BEFORE any batch cycle to avoid the c38-stale-data class of incident
(c44 S2: 8/9 MEDIUM-tier already-reassigned, snapshot un-refreshed since c38).

## Reference

- Workflow detail: [references/workflow.md](references/workflow.md)
- Origin RETEX: `_alire/02_LOGS/Journals/retex/RETEX_PDCA_LIAPROBE_FINGERPRINT_REBUILD_CYCLE38_2026-05-13.md`
- c44 RETEX (A62 doctrine first sustained use): `_alire/02_LOGS/Journals/retex/RETEX_PDCA_LIAPROBE_FINGERPRINT_REBUILD_CYCLE44_2026-05-14.md`
- c38 recovery script: `.claude/skills/liaprobe-fingerprint-rebuild/scripts/recover_lia_declined_aliases.py`
- c44 reusable filter: `scripts/enrich_orphan_v4_filter.py`
- c45 RECOVERY refresh: `scripts/refresh_recovery_candidates.py`
- mig 164 (c39): `cmd/sigma_web/migrations/164_vendor_alias_reassign_round3.sql` (7 MEDIUM-tier reassignments, manual)
