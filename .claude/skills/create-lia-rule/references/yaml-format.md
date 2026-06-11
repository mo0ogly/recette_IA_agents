# YAML Format - Regles critiques de la regle YAML

## MOTOR_FIX_010 - Logique Auditable (BLOQUANT)

```yaml
# INTERDIT - Logique cachee dans la collecte
where:
  rules:
    - is_compliant: eq: false               # VIOLATION
    - CVE_2025_1234_is_vulnerable: eq: true # VIOLATION

# OBLIGATOIRE - Logique auditable dans la regle
where:
  condition: and
  rules:
    - ObjectClass: eq: ProductName
    - version_lt(Version, "12.8.0.0"): eq: true  # Auditable
```

---

## MOTOR_FIX_003 - 5 Computed Fields Obligatoires

```yaml
output:
  computed:
    Severity: "if(condition, 'CRITICAL', 'MEDIUM')"
    RiskReason: "if(condition, 'Explication risque', 'Conforme')"
    RecommendedAction: "if(condition, 'Action corrective', 'Aucune')"
    DetectionLogic: "if(condition, 'Description detection', 'N/A')"
    ComplianceImpact: "if(condition, 'Impact conformite', 'Conforme')"
```

**Limitations computed fields:**
- SEULE fonction supportee: `if(condition, val_true, val_false)`
- PAS d'arithmetique: `field1 + field2` = ERROR
- PAS de concatenation multiple: `str1 + str2 + str3` = ERROR
- PAS de fonctions agregation: `count_true()`, `join_strings()` = N'EXISTENT PAS
- Strings statiques: wrapper dans `if()` obligatoire
  ```yaml
  # INTERDIT
  Impact: "Arbitrary code execution"
  # CORRECT
  Impact: "if(Version != '', 'Arbitrary code execution', 'Unknown')"
  ```
- Eviter `mot (` dans les textes statiques → validator detecte comme fonction (#25)
  Exemple piege: "endpoint (gpupdate" / "populated (Get-AD" / "installed (Get-Item"

---

## Champs Obligatoires

```yaml
id: A-{AXIS}-{TECH}-{Component}
title: "Titre descriptif en anglais"
status: stable           # Valeurs valides UNIQUEMENT: deprecated|experimental|stable|test
                         # INTERDIT: informational, draft, active, production (→ CRITICAL validator)
date: "YYYY-MM-DD"       # OBLIGATOIRE avec guillemets (sans guillemets = parse comme time.Time)
author: "LIA-Scan Rules Team"
rule_type: vulnerability|compliance|hunting|attack
level: critical|high|medium|low
target: {TECHNOLOGY}     # Utiliser ADDS (pas ActiveDirectory), POSTGRESQL, etc.

object_type_field: ObjectClass    # OBLIGATOIRE

metadata:
  category: "..."
  date: "YYYY-MM-DD"
  version: "1.0"

taxonomy:
  taxonomy: {TECHNOLOGY}
  taxonomy_short: {TECHSHORT}
  axis: {AxisName}
  axis_short: {AXISSHORT}
  block: {BlockName}
  block_short: {BLOCKSHORT}       # DOIT etre dans config/taxonomy/{TECH}_taxonomy.json
  component: {ComponentName}
  component_short: {COMPSHORT}

data_source:
  collection_script: "scripts/collect/{tech}/Collect-{Tech}.ps1"
  description: "..."
  collection_method: "PowerShell Script"
  type: collection
  collection_type: "STANDARD"
  required_fields:
    - ObjectClass
    - ...

compliance_mapping:      # LOWERCASE keys obligatoire
  anssi:
    - id: "R14"
      title: "..."
  pci_dss:               # PAS PCI_DSS
    - id: "6.2"
      requirement: "..."  # PAS control
  iso_27001:             # PAS ISO_27001
    - id: "A.12.6.1"
  mitre_attack:          # MITRE va ICI, PAS dans references:
    - tactic: "Privilege Escalation"
      technique: "T1068"
      name: "Exploitation for Privilege Escalation"
  # INTERDIT: section stig → integrer dans nist_800_53

references:              # URLs UNIQUEMENT - aucun dict, aucun objet MITRE
  - https://nvd.nist.gov/vuln/detail/CVE-XXXX-XXXXX
  - https://ubuntu.com/security/CVE-XXXX-XXXXX
  # INTERDIT dans references:
  # - technique: T1499.001          # DICT MITRE = REJET validator
  #   name: OS Exhaustion Flood     # → doit aller dans compliance_mapping.mitre_attack
  #   url: https://attack.mitre.org/...
```

**Erreurs frequentes champs:**
- `taxonomy.technology` et `taxonomy.category` manquants
- `output.include:` est l'ANCIEN format → utiliser `output.fields:` (FORMAT V2, seul valide)
- `pci_dss` avec cle `control` au lieu de `requirement`
- Section `classification:` est redondante avec `taxonomy:` → ne pas inclure
- Regles ADDS: utiliser `target: ADDS` (pas `ActiveDirectory`)
- ReportRule: champ `author` doit etre un email (ex: `mo0ogly@proton.me`)
- ReportRule: champ `technology` doit etre le short code taxonomie (ex: `ADDS` pas `ActiveDirectory`)

---

## output.fields - Regles de declaration

**REGLE CRITIQUE: Tout champ utilise dans `output.computed` DOIT etre declare dans `output.fields`.**

```yaml
# INTERDIT - CISControlID utilise dans computed mais absent de fields
output:
  computed:
    DetectionLogic: "if(is_compliant == false, 'Control ' + CISControlID + ' non-compliant', 'OK')"
  fields:
    AuditOutput: AuditOutput    # CISControlID manquant → CRITICAL "CHAMPS UTILISES NON DEFINIS"

# CORRECT - Tous les champs references dans computed sont declares
output:
  computed:
    DetectionLogic: "if(is_compliant == false, 'Control ' + CISControlID + ' non-compliant', 'OK')"
  fields:
    AuditOutput: AuditOutput
    CISControlID: CISControlID  # Declare car utilise dans computed
```

**Verification avant validation:**
```bash
# Extraire tous les noms de champs dans computed (hors strings entre quotes)
grep -A20 "computed:" rule.yml | grep -v "if(\|'[^']*'" | grep -oP '\b[A-Z][A-Za-z]+\b'
# Chaque nom trouve doit apparaitre dans output.fields
```

**Pas de renommage:**
```yaml
output:
  fields:
    Hostname: Hostname           # Meme nom input/output
    Version: Version             # PAS Server_Version: Version
```

---

## Fonctions de version pour CVE - Format Extended avec match

**TOUJOURS utiliser le format Sigma Extended (section match) pour les regles CVE multi-branch:**

```yaml
# PATTERN RECOMMANDE pour CVE PostgreSQL multi-branch
object_detection:
  match:
    ObjectClass:
      eq: "postgresql_instance"
  where:
    condition: and
    rules:
      - ObjectClass:
          eq: "postgresql_instance"
      - condition: or
        rules:
          # PostgreSQL 18.x vulnerable si MinorVersion <= 1
          - condition: and
            rules:
              - MajorVersion: {eq: "18"}
              - MinorVersion: {version_lte: "1"}
          # PostgreSQL 17.x vulnerable si MinorVersion <= 7
          - condition: and
            rules:
              - MajorVersion: {eq: "17"}
              - MinorVersion: {version_lte: "7"}
          # PostgreSQL 16.x vulnerable si MinorVersion <= 11
          - condition: and
            rules:
              - MajorVersion: {eq: "16"}
              - MinorVersion: {version_lte: "11"}

# Alternative pour produits non-PostgreSQL (Fortinet, Ivanti, etc.)
object_detection:
  match:
    ObjectClass:
      eq: "FortinetDevice"
  where:
    condition: and
    rules:
      - ObjectClass:
          eq: "FortinetDevice"
      - condition: or
        rules:
          - condition: and
            rules:
              - Version: {regex: '^7\.6\.'}
              - version_lt(Version, "7.6.6"): {eq: true}
          - condition: and
            rules:
              - Version: {regex: '^7\.4\.'}
              - version_lt(Version, "7.4.11"): {eq: true}
```

**IMPORTANT:** Toujours utiliser format `X.Y.Z` (3 segments minimum) pour les versions:
```yaml
# ECHOUE avec PostgreSQL 16.9
- Version: {version_lt: "16.10"}
# CORRECT
- Version: {version_lt: "16.10.0"}
```

---

## Attributs AD optionnels - Pattern or[|exists, isempty] (ADDS uniquement)

**ATTENTION CRITIQUE:** Les deux operateurs suivants sont COMPLEMENTAIRES, PAS interchangeables:
- `|exists: eq: false` → detecte uniquement les cles VRAIMENT ABSENTES du JSON (key not present)
- `isempty: true` → detecte uniquement les valeurs null/vides quand la CLE EXISTE dans le JSON

Selon le script de collecte PowerShell utilise:
- Certains scripts omettent la cle si l'attribut AD n'est pas renseigne → `|exists: eq: false`
- Certains scripts incluent la cle avec valeur `null` si l'attribut est absent → `isempty: true`
- En pratique les deux cas peuvent coexister dans le meme test_data.json

**PATTERN DEFINITIF OBLIGATOIRE (combine les deux):**

```yaml
# INTERDIT - Un seul operateur (incomplet)
where:
  rules:
    - LAPSPwdExpirationTime|exists:
        eq: false    # ECHOUE si le champ est present mais null
    - LAPSPwdExpirationTime:
        isempty: true    # ECHOUE si le champ est vraiment absent du JSON

# CORRECT - Combiner avec or (couvre tous les cas)
where:
  condition: and
  rules:
    - ObjectClass:
        eq: "computer"
    - condition: or
      rules:
        - LAPSPwdExpirationTime|exists:
            eq: false        # Cas 1: cle absente (key not in JSON)
        - LAPSPwdExpirationTime:
            isempty: true    # Cas 2: cle presente mais null/vide
```

**Comportements valides dans test_data.json:**
```json
// Cas 1: cle absente → detecte par |exists: false
{"ObjectClass": "computer", "Hostname": "pc-01", "_expected_match": true}

// Cas 2: cle presente avec null → detecte par isempty: true
{"ObjectClass": "computer", "Hostname": "pc-02", "LAPSPwdExpirationTime": null, "_expected_match": true}

// Cas 3: cle presente avec valeur → non detecte (SAFE)
{"ObjectClass": "computer", "Hostname": "pc-03", "LAPSPwdExpirationTime": "2026-06-01T00:00:00Z", "_expected_match": false}
```

**Attributs AD concernes:** `ms-Mcs-AdmPwdExpirationTime`, `msLAPS-PasswordExpirationTime`,
`servicePrincipalName`, `msDS-AllowedToDelegateTo`, `AdminCount`, `ManagedBy`.

---

## Operateurs et Fonctions NON IMPLEMENTES (INTERDIT d'utiliser)

**Source:** `_alire/01_DOCUMENTATION/rules/01_Guides/guides/operator_reference_table.md` + `_alire/01_DOCUMENTATION/technical/2_functions_available_tech_en.md` (73 operateurs implementes)

**Operateurs declares mais PAS implementes - provoquent une erreur silencieuse:**
```yaml
# INTERDIT - Modificateurs temporels (non implementes)
- EventDate:
    minute: gt: 5    # NOT IMPLEMENTED
    hour: lt: 2      # NOT IMPLEMENTED
    day: gte: 1      # NOT IMPLEMENTED
    week: eq: 1      # NOT IMPLEMENTED
    month: ne: 12    # NOT IMPLEMENTED
    year: eq: 2026   # NOT IMPLEMENTED

# INTERDIT - Encodage UTF-16 (non implemente)
- CommandLine:
    utf16le: contains: "powershell"   # NOT IMPLEMENTED
    wide: contains: "cmd"              # NOT IMPLEMENTED
    utf16be: contains: "exec"          # NOT IMPLEMENTED
    utf16: contains: "wscript"         # NOT IMPLEMENTED

# INTERDIT - Transformations string (non implementees)
- CommandLine:
    windash: contains: "-hidden"   # NOT IMPLEMENTED
    cased: eq: "PowerShell"        # NOT IMPLEMENTED

# INTERDIT - Regex avances (non implementes)
- Content:
    re.multiline: "^pattern$"   # NOT IMPLEMENTED
    re.dotall: ".*secret.*"     # NOT IMPLEMENTED

# INTERDIT - Expansion variable (non implementee)
- Path:
    expand: contains: "TEMP"   # NOT IMPLEMENTED
```

**Operateurs implementes equivalents (a utiliser a la place):**
- Temporel → utiliser `days_since()`, `age_in_months()`, `before`, `after`
- UTF-16 → utiliser `contains` ou `regex` apres normalisation
- Regex multiline → utiliser `regex` / `re` sur valeur normalisee
- Existence → utiliser `isempty: true` / `isnotempty: true` / `exists: true`

**Reference complete:** `_alire/01_DOCUMENTATION/rules/01_Guides/guides/operator_reference_table.md`
**Reference fonctions:** `_alire/01_DOCUMENTATION/technical/2_functions_available_tech_en.md`

---

## cve_info Block - Contrat de TYPE + enrichissement PostgreSQL (regles CVE)

**Incident 2026-05-29 (nightly harvest):** une regle ecrivait `kev_ransomware: 'Unknown'`
(string) alors que le moteur attend un **bool**. yaml.v2 echoue a unmarshal string->bool
et **droppe TOUTE la regle en silence** : le moteur charge `0 structured rules evaluated`,
0 matches, alors que `cvss_vector`/`kev_due_date` (strings) passaient. Plusieurs regles de
la nuit sont aussi sorties MAIGRES (sans `cvss_vector`/`kev_due_date`/`kev_ransomware`/EPSS)
alors que les donnees existaient en base.

### Contrat de type (struct `CVEInfo`, `pkg/model/sigmarule.go`) -- BLOQUANT

Ecrire le mauvais type = regle silencieusement non chargee par le moteur. Respecter EXACTEMENT :

| Champ cve_info | Type YAML | Exemple correct | Piege |
|----------------|-----------|-----------------|-------|
| `is_kev` | **bool** | `is_kev: true` | JAMAIS `'true'` ni `'Unknown'` |
| `kev_ransomware` | **bool** | `kev_ransomware: true` | DB `Known`->`true` ; `Unknown`/absent -> OMETTRE (pas `false`, pas `'Unknown'`) |
| `exploit_available` | **bool** | `exploit_available: true` | pas de string |
| `patch_available` | **bool** | `patch_available: true` | pas de string |
| `cvss_score` | **float** | `cvss_score: 9.8` | pas `'9.8'` |
| `epss_score` | **float** (0..1) | `epss_score: 0.94215` | pas `'0.94'` |
| `epss_percentile` | **float** (0..100) | `epss_percentile: 99.7` | pas string |
| `cwe` / `capec` / `owasp` / `affected_products` / `exploit_references` / `cve_aliases` | **array** | `cwe:\n  - CWE-89` | jamais scalaire |
| `cvss_version` `cvss_vector` `cvss_severity` `kev_date_added` `kev_due_date` `kev_description` `affected_versions` `fixed_versions` `exploit_maturity` `patch_url` `vendor_advisory` `published_date` `last_modified_date` `remediation_priority` `cve_id` | string | `kev_due_date: '2026-05-17'` | dates entre quotes |

Regle d'or bool : un bool ne prend QUE `true`/`false` non quotes. Une valeur tri-etat
("Known/Unknown/N/A") n'est PAS un bool -> mapper (`Known`->`true`) et OMETTRE sinon.

### Enrichissement PostgreSQL OBLIGATOIRE (ne pas livrer maigre)

Pendant la phase PostgreSQL FIRST, peupler cve_info avec TOUT ce qui existe en base :

```sql
SELECT n.cvss_score, n.cvss_severity, n.cvss_vector, n.cwe_ids,
       e.epss_score, e.epss_percentile, e.score_date AS epss_date,
       k.cve_id IS NOT NULL AS is_kev, k.date_added AS kev_date_added,
       k.due_date AS kev_due_date, k.known_ransomware_use AS kev_ransom,
       k.short_description AS kev_description
FROM cve_nvd_data n
LEFT JOIN epss_scores e ON e.cve_id = n.cve_id
LEFT JOIN kev_cisa_vulnerabilities k ON k.cve_id = n.cve_id
WHERE n.cve_id = 'CVE-YYYY-NNNNN';
```

Mapping vers cve_info :
- `cvss_vector` -> `cvss_vector` (string) ; `cwe_ids` (array Postgres `{CWE-89}`) -> `cwe:` (liste YAML)
- `epss_score`/`epss_percentile` -> floats ; `epss_date` -> string. Si EPSS vide en base -> OMETTRE (R4, ne pas inventer).
- KEV : `is_kev` bool, `kev_date_added`/`kev_due_date` strings, `kev_ransom == 'Known'` -> `kev_ransomware: true` sinon omis, `kev_description` string.
- Champ absent en base (CAPEC/OWASP/affected_products non presents dans ces tables) -> OMETTRE, ne jamais fabriquer.

### Cross-check rule vs NVD (BLOQUANT avant commit)

Comparer les valeurs de la regle a `cve_nvd_data`. Un desaccord = recherche, pas un choix au hasard :
- `cve_info.cwe` vs `cve_nvd_data.cwe_ids`
- `cve_info.cvss_version` vs prefixe de `cve_nvd_data.cvss_vector` (`CVSS:3.1` / `CVSS:4.0`)
- `cve_info.cvss_score` vs `cve_nvd_data.cvss_score`

Si mismatch (ex DMTL CVE-2026-8398 : regle `CWE-494`/CVSS 3.1 vs base `CWE-506`/CVSS 4.0) :
trancher via l'advisory vendor officiel + NVD, documenter la source dans RESEARCH_EVIDENCE.md,
PUIS aligner. Ne jamais committer deux verites contradictoires.
