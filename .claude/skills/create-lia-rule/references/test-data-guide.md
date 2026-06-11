# Test Data Guide - Phase 3

## REGLES ABSOLUES - Champ description et prefixes (Phase 12)

**Champ obligatoire:** `_test_description` (JAMAIS `_case_description`, `_description`, `comment`)
Phase 12 utilise `._test_description` en dur - tout autre nom = 0 vulnérables détectés.

**Prefixes OBLIGATOIRES:**
- Cas VULNERABLE: commencer par `"VULNERABLE"` (ex: `"VULNERABLE - Module not loaded"`)
- Cas SAFE: commencer par `"SAFE"`, `"PATCHED"`, `"NOT_VULNERABLE"`, ou `"NOT_APPLICABLE"`

```json
// CORRECT
{"_test_description": "VULNERABLE - AppArmor disabled at runtime", "_expected_match": true}
{"_test_description": "SAFE: AppArmor enabled with 12 enforce profiles", "_expected_match": false}

// INTERDIT - Phase 12 compte 0 vulnérables
{"_case_description": "VULNERABLE - ..."}
{"_test_description": "DETECTED: AppArmor absent"}
{"_test_description": "NOT_PROTECTED: Module not loaded"}
```

---

## GARDE-FOU CRITIQUE: Coherence champs test_data vs source identifiee

Les champs dans test_data.json DOIVENT correspondre EXACTEMENT a ceux decouverts en Phase 0
(script de collecte, regle existante, ou recherche internet).

**Verification OBLIGATOIRE avant ecriture test_data.json:**
```bash
# 1. Lire un test_data.json EXISTANT de la meme technologie (PREMIER REFLEXE)
Glob: lia_rules/rule_analysis/{TECHNOLOGY}/**/test_data.json
# SI trouve: copier la structure des champs (ObjectClass, Hostname, Version, etc.)
# SI pas trouve: utiliser les champs documentes dans RESEARCH_EVIDENCE.md (Phase 0, Niveau 3)

# 2. Verifier coherence bidirectionnelle:
# CHAQUE champ dans test_data.json doit etre dans la liste fields: de la regle
# CHAQUE champ dans object_detection.where doit etre present dans test_data.json
```

---

## ANTI-MOCK: Donnees inventees → REJET automatique

Les validators automatiques detecteront les donnees inventees:
- Domaines fictifs (corp.local, example.com, contoso.com) → WARNING
- IPs RFC 5737 (192.0.2.x, 198.51.100.x, 203.0.113.x) → REJET
- Hostnames sequentiels generiques (server01, server02...) → WARNING
- URLs placeholder (example.com, TODO, changeme) → REJET
- Homogeneite des domaines (tous le meme .corp.local) → WARNING

Les hostnames doivent etre DIVERSIFIES et REALISTES (ex: db-prod-paris, app-web-02, pgcluster-dr)

**INTERDIT - Champs inventes:**
```json
// INTERDIT - Champs inventes non collectes par le script
{"ObjectClass": "postgresql_extension", "ExtensionName": "anon", "ExtensionVersion": "2.0.0"}
// postgresql_extension N'EXISTE PAS dans Collect-PostgreSQL-Version.ps1
// ExtensionName et ExtensionVersion ne sont PAS collectes
```

**CORRECT - Champs reels:**
```json
// CORRECT - Champs reels du script de collecte
{"ObjectClass": "postgresql_instance", "Hostname": "db01.corp.local", "Version": "17.5",
 "MajorVersion": "17", "MinorVersion": "5", "Product": "PostgreSQL"}
// Tous ces champs existent dans la collecte postgresql_instance
```

---

## Minimum 14 cas realistes

Ratio obligatoire:
- 8-9 cas VULNERABLES (55-65%)
- 5-6 cas SECURISES (35-45%)
- 2-3 cas EDGE (decommissioned, null, inactive)

```json
[
  {
    "ObjectClass": "ProductName",
    "Hostname": "server01.corp.local",
    "Version": "12.5.0.0",
    "_expected_match": true,
    "Description": "VULNERABLE - Version 12.5 below fix 12.8.0"
  },
  {
    "ObjectClass": "ProductName",
    "Hostname": "server02.corp.local",
    "Version": "12.8.0.0",
    "_expected_match": false,
    "Description": "SAFE - Version 12.8.0 is the fix version - not impacted"
  },
  {
    "ObjectClass": "ProductName",
    "Hostname": "server03.corp.local",
    "Version": "13.0.0.0",
    "_expected_match": false,
    "Description": "SAFE - Version 13.0 above fix threshold - not impacted"
  }
]
```

---

## CRITICAL - Descriptions cas SAFE (ratio validateur)

Le validateur de ratio detecte les mots-cles `CVE|CRITICAL|HIGH|Vulnerable|Affected` dans le champ
`Description`/`comment` independamment du flag `_expected_match`. Un cas SAFE contenant le CVE ID
dans sa description est compte comme VULNERABLE, faussant le ratio (erreur HIGH).

Regles a respecter pour les descriptions de cas `_expected_match: false` :
- Ne JAMAIS mentionner le CVE ID (ex: "CVE-2025-27151") dans la description d'un cas SAFE
- Ne JAMAIS utiliser les mots "CRITICAL", "HIGH", "Vulnerable", "Affected" dans un cas SAFE
- Utiliser des formulations neutres : "not impacted", "below minimum affected version", "patched"

```json
// INTERDIT - compte comme VULNERABLE (contient le CVE ID)
{"_expected_match": false, "Description": "SAFE - Patched for CVE-2025-27151"}

// CORRECT - compte comme SAFE
{"_expected_match": false, "Description": "SAFE - Patched - below minimum affected version - not impacted"}
```

---

## Format BANK

Pour regles BANK: Format array direct, champ `Description` (pas `_comment`).

False positives a eviter:
- "SafeNet" → renommer en "Luna" si besoin
- Eviter les mots "insecure", "weak" dans les cas SAFE (detectes comme VULNERABLE)
