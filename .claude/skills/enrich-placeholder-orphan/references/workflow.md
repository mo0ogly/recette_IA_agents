# enrich-placeholder-orphan -- workflow detail

## Loop diagram

```
                    +---------------+
                    | INIT          | resolve placeholder ids
                    +-------+-------+
                            |
                    +-------v-------+
                    | FETCH ORPHAN  | next batch of N orphans
                    +-------+-------+
                            |
                +-----------v-----------+
                | EXTRACT TOKEN         | identify candidate target vendor
                +-----------+-----------+
                            |
            +---------------+---------------+
            |                               |
       NO TOKEN                        TOKEN FOUND
            |                               |
            v                               v
   SKIP_NONCANDIDATE             +---------------------+
                                  | NVD CVE COUNT QUERY |
                                  +----------+----------+
                                             |
                            +----------------+----------------+
                            |                                 |
                       count = 0                         count > 0
                            |                                 |
                            v                                 v
                  DEFER_DEAD_VENDOR              +-------------------------+
                                                  | WEBFETCH VENDOR DOC     |
                                                  | (sha256, cache)         |
                                                  +-----------+-------------+
                                                              |
                                                              v
                                                  +-------------------------+
                                                  | HUMAN CHECKPOINT        |
                                                  | ACCEPT / REJECT / DEFER |
                                                  +-----------+-------------+
                                                              |
                                          +-------------------+-------------------+
                                          |                                       |
                                       ACCEPT                                  REJECT
                                          |                                       |
                                          v                                       v
                              APPEND UPDATE TO MIG NNN                  LOG REASON, NEXT
                              + APPEND EVIDENCE BLOCK
                                          |
                                          v
                                  +--------------+
                                  | NEXT ORPHAN  |---> loop
                                  +------+-------+
                                         |
                                         v
                                   ALL PROCESSED
                                         |
                                         v
                                  +--------------+
                                  | RECETTE      | verify_engine_delta.sh
                                  +------+-------+
                                         |
                                         v
                                  +--------------+
                                  | COMMIT MIG   | apply + INDEX + RETEX
                                  +--------------+
```

## SQL templates

### Resolve placeholder ids

```sql
SELECT vendor_id, vendor_name FROM vendor
WHERE vendor_name IN ('lia-declined','lia-meta','Unknown-O')
ORDER BY vendor_name;
```

### Fetch next N orphans (paginate)

```sql
SELECT va.alias_name
FROM vendor_alias va
JOIN vendor v_placeholder ON v_placeholder.vendor_id = va.vendor_id
WHERE v_placeholder.vendor_name IN ('lia-declined','lia-meta','Unknown-O')
  AND NOT EXISTS (
    SELECT 1 FROM vendor v_real
    WHERE LOWER(v_real.vendor_name) = LOWER(va.alias_name)
      AND v_real.vendor_name NOT IN ('lia-declined','lia-meta','Unknown-O')
  )
ORDER BY va.alias_name
LIMIT N OFFSET O;
```

### NVD CVE count for candidate target

```sql
SELECT COUNT(*) FROM cve_nvd_data
WHERE LOWER(vendor) = LOWER(:candidate_vendor_name);
```

(`vendor` column in cve_nvd_data; confirm via `\d cve_nvd_data` before relying on the exact name.)

### Idempotent reassignment UPDATE

```sql
UPDATE vendor_alias
SET vendor_id = (SELECT vendor_id FROM vendor WHERE LOWER(vendor_name) = LOWER(:target) LIMIT 1),
    source = 'lia_manual_c{N}_reassign_orphan_enrich'
WHERE LOWER(alias_name) = LOWER(:alias)
  AND vendor_id = (SELECT vendor_id FROM vendor WHERE LOWER(vendor_name) = 'lia-declined' LIMIT 1);
```

### Final assertion (anti-typo guard)

```sql
DO $$
DECLARE expected INT := :expected_count;
DECLARE actual INT;
BEGIN
  SELECT COUNT(*) INTO actual FROM vendor_alias
  WHERE source = 'lia_manual_c{N}_reassign_orphan_enrich';
  IF actual <> expected THEN
    RAISE EXCEPTION 'Expected % reassignments, got %', expected, actual;
  END IF;
  RAISE NOTICE 'OK: % aliases reassigned', actual;
END $$;
```

## Evidence block template (per alias)

```markdown
### Alias: `lotus-domino` -> Vendor: `Lotus` (vid=95)

| Field | Value |
|-------|-------|
| Strategy | manual_token_extract |
| Candidate token | lotus |
| NVD CVE count for "Lotus" | 142 |
| Vendor doc URL | https://www.hcltech.com/products/domino |
| Page sha256 | abc123... |
| Verified at | 2026-05-13T20:00:00Z |
| Decision | ACCEPT |
| Rationale | Lotus Domino is HCL's email/collab product (formerly IBM). NVD lists 142 CVEs. The alias `lotus-domino` is unambiguous. |
```

## DEFER_DEAD_VENDOR JSON entry

```json
{
  "alias_name": "viavideo legacy device",
  "candidate_target": "ViaVideo",
  "nvd_cve_count": 0,
  "deferred_at": "2026-05-13T20:00:00Z",
  "reason": "candidate vendor has zero CVEs in NVD; no urgency. Revisit when NVD adds entries OR human triages."
}
```

## Recette gate

`vendor_alias` reassignments do NOT feed the fingerprint engine matcher (engine
uses `_meta_enrichment.canonical_vendor.product_name_db` from pattern files,
not the `vendor_alias` table). Therefore `verify_engine_delta.sh` MUST report
PRE = POST identically. Any drift = unrelated noise (e.g. nightly w0X loop
committed a pattern change between baseline and post). Investigate but do not
attribute to this skill.

## Konrad-kurze invocation criteria

Trigger `/konrad-kurze` (scope = current session) when:
- 3 successive orphans return the same SKIP_NONCANDIDATE verdict from the
  same extraction strategy (suggests strategy is structurally inadequate
  for the current orphan distribution).
- 5 successive WebFetch attempts return paywalled / login-required pages
  (suggests batch is wrong scope: paywalled vendors should be DEFER_DEAD).
- Human checkpoint REJECT rate exceeds 50% over last 10 proposals (skill
  is producing noise).

## Filter calibration history

| Version | Cycle | Rules | Effect |
|---------|-------|-------|--------|
| v1 | c40 pilot | raw ILIKE substring | 0 raw ACCEPT on 5 (no FP, no TP) |
| v2 | c41 batch | min token len 3 + ILIKE | 4 raw ACCEPT on 10, 100% FP |
| v3 | c42 batch | min token len 4 + word boundary regex `~* '\m...\M'` + stop_words v3 | 1 raw ACCEPT on 15, 100% FP |
| v4 | c43 batch | v3 + expanded stop_words v4 (8 new generic descriptors) | TBD |

### Stop words v3 (c42 baseline)

```
inc, ltd, corp, gmbh, ag, group, sa, sas, bv, llc, the, com, www
```

### Stop words v4 (c43 expansion)

Adds 8 generic descriptors that match many unrelated vendors (causing FP class
"Deutsche Post matched on `deutsche`" in c42 A60):

```
deutsche       # matches Deutsche Post/Telekom/many "Deutsche X"
international  # matches IBM/HP/etc.
global         # generic descriptor
systems        # matches many "X Systems"
technology     # matches many "X Technology"
networks       # matches Cisco Networks, Juniper Networks, etc.
software       # matches Adobe Software, etc.
solutions      # generic descriptor
```

### Token filter pseudocode (v4)

```python
STOP_WORDS_V4 = {
    "inc","ltd","corp","gmbh","ag","group","sa","sas","bv","llc","the","com","www",
    "deutsche","international","global","systems","technology","networks","software","solutions",
}

def extract_tokens(alias: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", alias.lower())
    return [t for t in tokens if len(t) >= 4 and t not in STOP_WORDS_V4]

def filter_candidates_v4(tokens: list[str]) -> list[CandidateRow]:
    return [c for tok in tokens
              for c in psql_lia(
                  "SELECT vendor_id, vendor_name, cve_count FROM vendor_with_cves "
                  "WHERE vendor_name ~* %s ORDER BY cve_count DESC LIMIT 5",
                  rf'\m{re.escape(tok)}\M',
              )
              if c.cve_count > 0]
```

### Calibration verdict (after c40+c41+c42)

0/30 verified ACCEPTs across 3 batches with v1/v2/v3. NONE-tier orphans dominated
by truly NVD-absent vendors. **c43 strategy**: mass `permanent_doubtful` migration
for remaining NONE-tier aliases (mig 166 A64). LOW-tier 47 candidates (substring
matches from c38 RECOVERY) still worth a single batch pass at v4 (mig 167+).

### Stop words v5 / WEAK_TOKENS (c44)

c44 A69 added a second tier: WEAK_TOKENS. These pass the v4 stop-word filter
(they are 4+ chars, alphanumeric, not in v4 stop list) but are too generic to
act as a unique semantic-owner signal on their own. If the matched-token set
is entirely contained in WEAK_TOKENS, the verdict is demoted from PASS to
SUBSTRING_FP.

```
corporation, electronics, laboratories, industries,
plugin, plugins, vacation, unknown, white, penguin,
fritz, stephen, domain, rentals
```

Calibrated against c43 LOW-tier 47 batch: WEAK_TOKENS eliminated 12 PASS
verdicts that were all FPs (`vdr-plugin-live -> Plugin`, `c-phone corporation
-> Sct Corporation`, etc.) while preserving genuine 0.5-overlap matches like
`lotus-domino -> Lotus`.

### Reusable script

`scripts/enrich_orphan_v4_filter.py` bakes the v4+v5 filter logic. CLI:

```bash
# Single pair
python3 scripts/enrich_orphan_v4_filter.py --alias "sork-vacation-h3" --candidate "Horde"

# Batch JSON
python3 scripts/enrich_orphan_v4_filter.py --batch path/to/batch.json --json-out

# Self-test (regression guard against c43 LOW-tier baseline)
python3 scripts/enrich_orphan_v4_filter.py --self-test
# Expected: 0 PASS, 29 NO_MATCH, 17 SUBSTRING_FP, 1 STOPWORD_FP on c43 47-batch
```

Self-test is the regression guard. Any change to STOP_WORDS_V4 / WEAK_TOKENS /
MIN_SEMANTIC_OVERLAP must keep the c43 baseline output (zero PASS).

## Future improvements (queued for c44+)

- LLM-assisted token extraction for ambiguous aliases (e.g.
  `apache_http_server_a` -> dual-token: Apache + HTTP Server).
- pg_trgm pre-filter to skip aliases too distant from any real vendor name
  (CASE WHEN max similarity < 0.3 -> SKIP_NONCANDIDATE).
- Batch import from CISA KEV / Exploit-DB to identify high-priority orphans
  first.
