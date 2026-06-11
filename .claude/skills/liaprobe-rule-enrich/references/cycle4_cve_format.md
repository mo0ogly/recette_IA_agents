# Cycle 4 -- CVE Awareness Format

## Schema target -- known_cves[]

Inject within fingerprint JSON :

```json
"known_cves": [
  {
    "cve_id": "CVE-2024-12345",
    "severity": "HIGH",
    "cvss_v3": 8.1,
    "published": "2024-09-12",
    "cisa_kev": true,
    "kev_date_added": "2024-09-15",
    "exploit_db_id": 51234,
    "exploit_maturity": "WEAPONIZED"
  }
]
```

Fields :
- `cve_id` (required) : CVE identifier
- `severity` : LOW / MEDIUM / HIGH / CRITICAL
- `cvss_v3` : CVSS v3.x base score 0.0-10.0
- `published` : ISO date
- `cisa_kev` : boolean, true if in CISA Known Exploited Vulnerabilities catalog
- `kev_date_added` : ISO date if cisa_kev=true
- `exploit_db_id` : Exploit-DB integer ID if exploit available
- `exploit_maturity` : THEORETICAL / PROOF_OF_CONCEPT / AUTOMATED / WEAPONIZED / IN_THE_WILD

## SQL query template

```sql
SELECT
  c.cve_id,
  c.cvss_v3_severity AS severity,
  c.cvss_v3_base_score AS cvss,
  c.description,
  c.published_date,
  (k.cve_id IS NOT NULL) AS in_kev,
  k.date_added AS kev_date_added,
  e.exploit_db_id,
  e.exploit_maturity
FROM cve_nvd_data c
LEFT JOIN cisa_kev k ON k.cve_id = c.cve_id
LEFT JOIN exploit_db_meta e ON e.cve_id = c.cve_id
WHERE c.cpe23 LIKE 'cpe:2.3:a:vendor:product:%'
ORDER BY in_kev DESC NULLS LAST, c.cvss_v3_base_score DESC NULLS LAST
LIMIT 50;
```

## Limits

- Max 50 entries per signature (sorted KEV first, then CVSS desc)
- Skip if no `cpe23_template` present
- Skip if 0 CVE matched
