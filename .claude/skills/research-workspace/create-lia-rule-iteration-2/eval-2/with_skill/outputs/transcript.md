# Analyse du test_data.json - CVE-2025-47812 (Wing FTP Server)

## Verdict : ECHEC DE VALIDATION GARANTI - Phase 12 (ratio validateur)

Ton test_data.json va echouer la Phase 12 de `validate_rules_recipe.sh`. Voici l'analyse complete.

---

## Probleme identifie : CVE-ID dans les descriptions SAFE

### Mecanisme du validateur de ratio (Phase 12)

Le validateur detecte les mots-cles suivants dans le champ `Description` :

```
CVE | CRITICAL | HIGH | Vulnerable | Affected
```

Cette detection est **independante du flag `_expected_match`**. Autrement dit, si un cas `_expected_match: false` contient "CVE-2025-47812" dans sa description, le validateur le COMPTE comme un cas vulnerable, pas comme un cas safe.

Resultat : le ratio vulnerable/safe est fausse, et la Phase 12 retourne une erreur HIGH.

---

## Diagnostic cas par cas - descriptions SAFE

Voici l'etat actuel de tes 6 cas `_expected_match: false` :

| Hostname | Description actuelle | Probleme | Severite |
|---|---|---|---|
| ftp-sec-01 | "SAFE - Patched for CVE-2025-47812 - version 7.4.0" | Contient "CVE-2025-47812" | HIGH |
| ftp-sec-02 | "SAFE - CVE-2025-47812 does not affect version 7.5.0" | Contient "CVE-2025-47812" | HIGH |
| ftp-sec-03 | "SAFE - Major version above CVE-2025-47812 affected range" | Contient "CVE-2025-47812" + "affected" | HIGH |
| ftp-cloud-01 | "SAFE - Patched version, CVE-2025-47812 not applicable" | Contient "CVE-2025-47812" | HIGH |
| ftp-legacy-01 | "SAFE - Version null, decommissioned instance" | Aucun mot interdit | OK |
| ftp-legacy-02 | "SAFE - Empty version, offline instance" | Aucun mot interdit | OK |

4 cas sur 6 sont defaillants. Avec 8 cas vulnerables reels et 4 faux-positifs detectes par le validateur, le ratio calcule sera :

- Vulnerables detectes par validateur : 8 + 4 = 12
- Safes detectes par validateur : 2
- Ratio resultant : 85.7% vulnerables (attendu : 55-65%)
- Erreur Phase 12 : HIGH - ratio hors plage

---

## Corrections

Remplacer les 4 descriptions SAFE defaillantes par des formulations neutres :

```json
[
  {"ObjectClass": "wftps_instance", "Hostname": "ftp-prod-01", "Version": "7.2.0", "_expected_match": true, "Description": "VULNERABLE - Version 7.2.0 below fix threshold 7.4.0"},
  {"ObjectClass": "wftps_instance", "Hostname": "ftp-prod-02", "Version": "7.1.5", "_expected_match": true, "Description": "VULNERABLE - Version 7.1.5 below fix threshold 7.4.0"},
  {"ObjectClass": "wftps_instance", "Hostname": "ftp-prod-03", "Version": "7.3.9", "_expected_match": true, "Description": "VULNERABLE - Version 7.3.9 below fix threshold 7.4.0"},
  {"ObjectClass": "wftps_instance", "Hostname": "ftp-prod-04", "Version": "7.0.0", "_expected_match": true, "Description": "VULNERABLE - Version 7.0.0 below fix threshold 7.4.0"},
  {"ObjectClass": "wftps_instance", "Hostname": "ftp-dev-01", "Version": "6.9.0", "_expected_match": true, "Description": "VULNERABLE - Version 6.9.0 below fix threshold 7.4.0"},
  {"ObjectClass": "wftps_instance", "Hostname": "ftp-staging-01", "Version": "7.3.0", "_expected_match": true, "Description": "VULNERABLE - Version 7.3.0 below fix threshold 7.4.0"},
  {"ObjectClass": "wftps_instance", "Hostname": "ftp-backup-01", "Version": "7.2.8", "_expected_match": true, "Description": "VULNERABLE - Version 7.2.8 below fix threshold 7.4.0"},
  {"ObjectClass": "wftps_instance", "Hostname": "ftp-backup-02", "Version": "7.1.0", "_expected_match": true, "Description": "VULNERABLE - Version 7.1.0 below fix threshold 7.4.0"},
  {"ObjectClass": "wftps_instance", "Hostname": "ftp-sec-01", "Version": "7.4.0", "_expected_match": false, "Description": "SAFE - Patched version 7.4.0 - not impacted"},
  {"ObjectClass": "wftps_instance", "Hostname": "ftp-sec-02", "Version": "7.5.0", "_expected_match": false, "Description": "SAFE - Compliant version 7.5.0 - not impacted"},
  {"ObjectClass": "wftps_instance", "Hostname": "ftp-sec-03", "Version": "8.0.0", "_expected_match": false, "Description": "SAFE - Major version above minimum affected version threshold - not impacted"},
  {"ObjectClass": "wftps_instance", "Hostname": "ftp-cloud-01", "Version": "7.4.1", "_expected_match": false, "Description": "SAFE - Patched - compliant version - not impacted"},
  {"ObjectClass": "wftps_instance", "Hostname": "ftp-legacy-01", "Version": null, "_expected_match": false, "Description": "SAFE - Version null, decommissioned instance"},
  {"ObjectClass": "wftps_instance", "Hostname": "ftp-legacy-02", "Version": "", "_expected_match": false, "Description": "SAFE - Empty version, offline instance"}
]
```

---

## Recap des changements

Modifications UNIQUEMENT sur les 4 cas `_expected_match: false` defaillants :

| Hostname | Avant | Apres |
|---|---|---|
| ftp-sec-01 | "...Patched for CVE-2025-47812..." | "...Patched version 7.4.0 - not impacted" |
| ftp-sec-02 | "...CVE-2025-47812 does not affect..." | "...Compliant version 7.5.0 - not impacted" |
| ftp-sec-03 | "...above CVE-2025-47812 affected range" | "...above minimum affected version threshold - not impacted" |
| ftp-cloud-01 | "...CVE-2025-47812 not applicable" | "...Patched - compliant version - not impacted" |

Les 8 cas `_expected_match: true` et les 2 cas SAFE sans mot interdit (ftp-legacy-01, ftp-legacy-02) sont conserves sans modification.

---

## Regle mnemonique

Pour tout cas `_expected_match: false` :
- **Interdit** : CVE-XXXX-XXXXX, CRITICAL, HIGH, Vulnerable, Affected
- **Autorise** : patched, not impacted, compliant version, below minimum affected version, decommissioned, offline, fixed

La description doit etre lisible par un auditeur sans mentionner le vecteur d'attaque. C'est le cas SAFE - il est propre, pas besoin de rappeler quel CVE il evite.
