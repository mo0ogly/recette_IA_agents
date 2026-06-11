# Schema PostgreSQL LIA-Scan — Reference pour SOUL.md

## Table cve_nvd_data

```sql
cve_id           VARCHAR(20)   -- ex: CVE-2025-21311
description      TEXT
cvss_score       DOUBLE        -- ex: 9.8
cvss_severity    VARCHAR(20)   -- CRITICAL / HIGH / MEDIUM / LOW
cvss_vector      TEXT          -- ex: CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H
published_date   TIMESTAMP
last_modified    TIMESTAMPTZ
cve_state        VARCHAR(20)   -- Analyzed / Modified / Awaiting Analysis
cwe_ids          TEXT[]
priority_level   VARCHAR(20)
cvss_te          DOUBLE        -- CVSS Temporal/Environmental
```

Colonnes INEXISTANTES (ne pas utiliser) :
- cvss_v3_score (-> cvss_score)
- cvss_v3_vector (-> cvss_vector)
- cisa_kev (-> jointure kev_cisa_vulnerabilities)
- patch_available (n'existe pas)

## Table kev_cisa_vulnerabilities

```sql
cve_id           VARCHAR(20)
vendor_project   TEXT
product          TEXT
vulnerability_name TEXT
date_added       DATE
short_description TEXT
required_action  TEXT
due_date         DATE
```

## Requete standard CVE (correcte)

```sql
SELECT
    n.cve_id,
    n.description,
    n.cvss_score,
    n.cvss_severity,
    n.cvss_vector,
    n.published_date,
    n.cve_state,
    CASE WHEN k.cve_id IS NOT NULL THEN 'true' ELSE 'false' END AS cisa_kev
FROM cve_nvd_data n
LEFT JOIN kev_cisa_vulnerabilities k ON n.cve_id = k.cve_id
WHERE n.cve_id = 'CVE-XXXX-XXXXX';
```

## Commande exec complete (copier-coller dans SOUL.md)

```json
{
  "tool": "exec",
  "command": "docker exec lia_postgres psql -U lia_admin -d lia_scan -c \"SELECT n.cve_id, n.description, n.cvss_score, n.cvss_severity, n.cvss_vector, n.published_date, n.cve_state, CASE WHEN k.cve_id IS NOT NULL THEN 'true' ELSE 'false' END AS cisa_kev FROM cve_nvd_data n LEFT JOIN kev_cisa_vulnerabilities k ON n.cve_id = k.cve_id WHERE n.cve_id = 'CVE-XXXX-XXXXX';\"",
  "workdir": "/home/mo0ogly/Bureau/vscode_lia_audit"
}
```

## Requete CVEs non traitees (pour heartbeat HERMES)

```sql
SELECT cve_id, cvss_score, cvss_severity, published_date
FROM cve_nvd_data
WHERE cvss_score >= 7.0
  AND cve_id NOT IN (
    SELECT DISTINCT regexp_matches(content, 'CVE-[0-9]{4}-[0-9]+')::text
    FROM ... -- verifier via find lia_rules/
  )
ORDER BY cvss_score DESC
LIMIT 10;
```

Note : pour verifier les CVEs non traitees, prefer la commande find :
```json
{
  "tool": "exec",
  "command": "docker exec lia_postgres psql -U lia_admin -d lia_scan -c \"SELECT cve_id, cvss_score, cvss_severity FROM cve_nvd_data WHERE cvss_score >= 7.0 ORDER BY cvss_score DESC LIMIT 20;\"",
  "workdir": "/home/mo0ogly/Bureau/vscode_lia_audit"
}
```
