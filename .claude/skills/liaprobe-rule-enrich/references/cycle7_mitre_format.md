# Cycle 7 -- MITRE ATT&CK Format

Source of truth: `scripts/enrich_cycle_7_mitre.py`.

Depends on Cycle 4: reads `rule.known_cves[]`. With no populated CVE list the
cycle is skipped (`reason: no_cves`).

## Schema target -- attack_surface{}

Injected at the top level of the fingerprint JSON as `rule.attack_surface`:

```json
"attack_surface": {
  "data_source": "cve_attack_mapping",
  "techniques": [
    { "id": "T1190", "stix_id": "attack-pattern--...", "name": "Exploit Public-Facing Application" }
  ],
  "techniques_count": 1,
  "cve_source_count": 12
}
```

Fields:
- `data_source` : always `"cve_attack_mapping"`.
- `techniques[]` : per entry
  - `id` : `technique_short_id` (e.g. `T1190`), falling back to
    `technique_id` if the short id is absent.
  - `stix_id` : the STIX `technique_id`.
  - `name` : `technique_name`.
- `techniques_count` : length of `techniques[]` (capped, see Limits).
- `cve_source_count` : number of CVE ids fed into the query.

## PostgreSQL query

```sql
SELECT DISTINCT
  technique_id,
  technique_short_id,
  technique_name
FROM cve_attack_mapping
WHERE cve_id = ANY(%(cve_ids)s)
ORDER BY technique_short_id
LIMIT %(limit)s;
```

`cve_ids` = the `cve_id` values from `rule.known_cves[]`. DB `lia_scan`.

## Skip conditions (non-fail)

- `no_cves` : `known_cves[]` empty -> run Cycle 4 first.
- `pg_down` : PostgreSQL unavailable (`DependencyMissingError`).
- `no_match` : 0 technique mapped from the CVE list.

## Limits

- `MAX_TECHNIQUES = 30` techniques per signature.
- No tactic/D3FEND fields are emitted by the current implementation; the
  block is technique-centric. Extend the query + `techniques[]` projection if
  tactic enrichment is added later.
