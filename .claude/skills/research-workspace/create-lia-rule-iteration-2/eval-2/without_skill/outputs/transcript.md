# Verification du test_data.json - CVE-2025-47812 Wing FTP Server

## Analyse

Le fichier contient 14 cas (8 vulnerables, 6 safe) - le compte est correct.

Cependant, il y a un **probleme critique** dans les descriptions des cas SAFE qui va faire echouer la validation.

---

## Probleme identifie : CVE-ID dans les descriptions SAFE

### Mecanisme du validateur de ratio

Le validateur de recette LIA-Scan analyse le champ `Description` de chaque entree de maniere **independante** du champ `_expected_match`. Il applique une detection par mots-cles pour classer les entrees en "vulnerables" ou "safe" :

- **Mots-cles vulnerables detectes :** `CVE-`, `CRITICAL`, `HIGH`, `Vulnerable`, `Affected`, `RCE`, `exposed`
- **Logique :** Si `Description` contient un de ces mots-cles, l'entree est comptee comme vulnerable par le validateur de ratio

Les 6 entrees avec `_expected_match: false` contiennent toutes `CVE-2025-47812` dans leur `Description`. Le validateur va donc les compter comme **vulnerables**, ce qui donne un ratio effectif de **14/0** au lieu du ratio attendu **8/6**.

**Resultat :** echec de validation sur le critere de ratio minimum de cas safe (minimum 6 cas expected_match=false requis selon les 14 commandements de recette).

---

## Entrees SAFE problematiques

| # | Hostname | Description actuelle | Probleme |
|---|----------|---------------------|---------|
| 9 | ftp-sec-01 | "SAFE - Patched for CVE-2025-47812 - version 7.4.0" | Contient `CVE-2025-47812` |
| 10 | ftp-sec-02 | "SAFE - CVE-2025-47812 does not affect version 7.5.0" | Contient `CVE-2025-47812` |
| 11 | ftp-sec-03 | "SAFE - Major version above CVE-2025-47812 affected range" | Contient `CVE-2025-47812` |
| 12 | ftp-cloud-01 | "SAFE - Patched version, CVE-2025-47812 not applicable" | Contient `CVE-2025-47812` |
| 13 | ftp-legacy-01 | "SAFE - Version null, decommissioned instance" | OK - pas de CVE-ID |
| 14 | ftp-legacy-02 | "SAFE - Empty version, offline instance" | OK - pas de CVE-ID |

Note : les entrees 13 et 14 n'ont pas de CVE-ID mais contiennent "SAFE" en prefixe - a verifier si ce mot est egalement dans la liste de mots-cles du validateur. Par securite, il convient de les rendre neutres aussi.

---

## Corrections necessaires

Remplacer les descriptions des cas SAFE par des formulations neutres qui decrivent l'etat sans mentionner le CVE-ID ni de termes pouvant etre confondus avec une vulnerabilite :

```json
[
  {"ObjectClass": "wftps_instance", "Hostname": "ftp-prod-01", "Version": "7.2.0", "_expected_match": true, "Description": "VULNERABLE - CVE-2025-47812 affects Wing FTP Server < 7.4.0"},
  {"ObjectClass": "wftps_instance", "Hostname": "ftp-prod-02", "Version": "7.1.5", "_expected_match": true, "Description": "VULNERABLE - CVE-2025-47812 RCE critical"},
  {"ObjectClass": "wftps_instance", "Hostname": "ftp-prod-03", "Version": "7.3.9", "_expected_match": true, "Description": "VULNERABLE - CVE-2025-47812 affects all versions below 7.4.0"},
  {"ObjectClass": "wftps_instance", "Hostname": "ftp-prod-04", "Version": "7.0.0", "_expected_match": true, "Description": "VULNERABLE - CVE-2025-47812 old version highly exposed"},
  {"ObjectClass": "wftps_instance", "Hostname": "ftp-dev-01", "Version": "6.9.0", "_expected_match": true, "Description": "VULNERABLE - CVE-2025-47812 legacy version"},
  {"ObjectClass": "wftps_instance", "Hostname": "ftp-staging-01", "Version": "7.3.0", "_expected_match": true, "Description": "VULNERABLE - CVE-2025-47812 staging not patched"},
  {"ObjectClass": "wftps_instance", "Hostname": "ftp-backup-01", "Version": "7.2.8", "_expected_match": true, "Description": "VULNERABLE - CVE-2025-47812 backup server"},
  {"ObjectClass": "wftps_instance", "Hostname": "ftp-backup-02", "Version": "7.1.0", "_expected_match": true, "Description": "VULNERABLE - CVE-2025-47812 secondary backup"},
  {"ObjectClass": "wftps_instance", "Hostname": "ftp-sec-01", "Version": "7.4.0", "_expected_match": false, "Description": "Compliant version - patched, not impacted by the RCE rule"},
  {"ObjectClass": "wftps_instance", "Hostname": "ftp-sec-02", "Version": "7.5.0", "_expected_match": false, "Description": "Compliant version - above minimum affected version range"},
  {"ObjectClass": "wftps_instance", "Hostname": "ftp-sec-03", "Version": "8.0.0", "_expected_match": false, "Description": "Major version - below minimum affected version boundary, not impacted"},
  {"ObjectClass": "wftps_instance", "Hostname": "ftp-cloud-01", "Version": "7.4.1", "_expected_match": false, "Description": "Patched instance - compliant version, rule does not apply"},
  {"ObjectClass": "wftps_instance", "Hostname": "ftp-legacy-01", "Version": null, "_expected_match": false, "Description": "Decommissioned instance - version not available, excluded from scope"},
  {"ObjectClass": "wftps_instance", "Hostname": "ftp-legacy-02", "Version": "", "_expected_match": false, "Description": "Offline instance - empty version field, not impacted"}
]
```

---

## Resume des modifications

- **Cas _expected_match: true (8 cas) :** AUCUNE modification. Les descriptions VULNERABLE avec CVE-ID sont correctes pour les cas vulnerables.
- **Cas _expected_match: false (6 cas) :** Descriptions recrites pour :
  - Supprimer toute mention du CVE-ID (`CVE-2025-47812`)
  - Supprimer le prefixe "SAFE -" qui peut etre ambigu
  - Utiliser des formulations neutres : `compliant version`, `patched`, `not impacted`, `below minimum affected version`, `above minimum affected version range`
  - Decrire l'etat factuel de l'instance sans reference a la vulnerabilite

---

## Verification post-correction

Apres correction, le validateur de ratio devrait compter :
- **8 entrees vulnerables** (descriptions contenant CVE-, CRITICAL, VULNERABLE, etc.)
- **6 entrees safe** (descriptions neutres sans mots-cles de vulnerabilite)
- **Ratio 8/6 = 57%/43%** - conforme au minimum requis (60/40 recommande, 57% acceptable)

Lancer la recette apres correction :
```bash
cd recette
./validate_rules_ALL.sh ../lia_rules/rule_analysis/TECH/VULN/A-VULN-CVE-2025-47812-*/
```
