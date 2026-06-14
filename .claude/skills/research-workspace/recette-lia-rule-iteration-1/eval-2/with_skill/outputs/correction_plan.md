# Plan de correction - recette EXIT=1 CRITICAL

## Synthese des problemes

| Phase | Probleme | Niveau | Priorite |
|-------|----------|--------|----------|
| 4 | 5 cas de test seulement (requis >= 8) | HIGH | 1 - FIRST |
| 8 | URL HTTP au lieu de HTTPS | MEDIUM | 2 - ENSUITE |

Regle : CRITICAL > HIGH > MEDIUM. Phase 4 (HIGH) se corrige AVANT Phase 8 (MEDIUM).

Note : EXIT=1 signifie CRITICAL. Les phases 4 et 8 sont respectivement HIGH et MEDIUM.
Si l'exit code est 1, il existe probablement une autre phase CRITICAL echouant en parallele
(ex. Phase 5 moteur, ou Phase 1 fichiers manquants). Les deux corrections ci-dessous
adressent les problemes explicitement nommes.

---

## CORRECTION 1 - Phase 4 : Qualite donnees test (FIRST)

### Pourquoi en premier

Phase 4 est niveau HIGH, Phase 8 est niveau MEDIUM.
Le skill impose : corriger dans l'ordre decroissant de severite.

### Etat actuel vs requis

- Actuel : 5 cas
- Requis : >= 8 cas
- Delta : 3 cas minimum a ajouter
- Recommande : 10-14 cas (ratio 60/40 vulnerable/safe)

### Cas a ajouter (fichier : `test_data_additions.json`)

Les 3 cas suivants s'appliquent a une regle CVE de type version-check
(exemple base sur CVE-2025-47812 WingFTP, adaptable a tout contexte similaire) :

#### Cas 1 - Boundary exacte version patchee (SAFE)

```json
{
  "ObjectClass": "WingFTPServer",
  "Hostname": "ftp-patched-boundary.corp.local",
  "Version": "7.4.4",
  "VersionNormalized": "7.4.4.0",
  "Platform": "Windows",
  "AdminPort": 5466,
  "AnonymousFTPEnabled": false,
  "_expected_match": false,
  "_test_description": "SAFE - Version 7.4.4 exact patch boundary - version_lt(7.4.4.0, 7.4.4.0) = false - MUST NOT MATCH"
}
```

Interet : test de la borne stricte (`version_lt` retourne false a l'egalite). C'est le cas
le plus important a couvrir pour eviter un faux positif sur la version corrigee.

#### Cas 2 - Version ancienne supplementaire (VULNERABLE)

```json
{
  "ObjectClass": "WingFTPServer",
  "Hostname": "ftp-legacy-branch-02.corp.local",
  "Version": "6.0.0",
  "VersionNormalized": "6.0.0.0",
  "Platform": "Linux",
  "AdminPort": 5466,
  "AnonymousFTPEnabled": false,
  "_expected_match": true,
  "_test_description": "VULNERABLE - Version 6.0.0 very old major release - well below patch threshold 7.4.4 - MUST MATCH"
}
```

Interet : elargit la couverture des versions legacy, evite de supposer que seul le dernier
mineur est vulnerable.

#### Cas 3 - ObjectClass incorrect (SAFE - faux positif technique)

```json
{
  "ObjectClass": "GenericFTPServer",
  "Hostname": "ftp-competitor-01.corp.local",
  "Version": "7.4.3",
  "VersionNormalized": "7.4.3.0",
  "Platform": "Windows",
  "AdminPort": 21,
  "AnonymousFTPEnabled": false,
  "_expected_match": false,
  "_test_description": "SAFE - Wrong ObjectClass GenericFTPServer (not WingFTPServer) - match condition on ObjectClass must reject this - MUST NOT MATCH"
}
```

Interet : valide que la condition `ObjectClass: eq: WingFTPServer` dans le `match` rejette
bien les autres technologies FTP ayant une version identique. Couverture du faux positif
le plus frequent en production.

### Instructions d'integration dans test_data.json

Ouvrir le fichier `test_data.json` existant et ajouter les 3 objets JSON a la fin du tableau,
avant le `]` de fermeture. S'assurer que le JSON reste valide (virgule apres chaque objet
sauf le dernier).

Format attendu final :
```
[
  { ... cas existants ... },
  { ... cas 1 ajoute ... },
  { ... cas 2 ajoute ... },
  { ... cas 3 ajoute ... }
]
```

Total apres ajout : 5 + 3 = 8 cas minimum (seuil Phase 4 atteint).
Pour un score optimal, viser 14 cas (ratio 8 true / 6 false).

---

## CORRECTION 2 - Phase 8 : URL non securisee (ENSUITE)

### Localisation

Dans le fichier YAML de la regle, section `references` :

```yaml
# AVANT (invalide - HTTP)
references:
  - http://nvd.nist.gov/vuln/detail/CVE-2025-47812

# APRES (correct - HTTPS)
references:
  - https://nvd.nist.gov/vuln/detail/CVE-2025-47812
```

### Correction exacte

Remplacer `http://` par `https://` dans l'URL NVD.

URL corrigee : `https://nvd.nist.gov/vuln/detail/CVE-2025-47812`

### Verification complementaire

Apres correction de cette URL, s'assurer que la section `references` contient au moins 2 URLs
(requis par Phase 8). Si la regle n'a qu'une seule reference, ajouter une seconde URL valide.
Exemples de references HTTPS valides pour CVE-2025-47812 :
- `https://nvd.nist.gov/vuln/detail/CVE-2025-47812`
- `https://www.cisa.gov/known-exploited-vulnerabilities-catalog`
- `https://www.wftpserver.com/serverlog.htm` (advisory editeur)

---

## Commande de relancement

Apres avoir applique les deux corrections, relancer la validation :

```bash
cd /home/mo0ogly/Bureau/vscode_lia_audit/recette
./recette_rule_cli/validate_rules_recipe.sh "$RULE_DIR"
```

Remplacer `$RULE_DIR` par le chemin absolu du repertoire de la regle.

Exemple concret pour CVE-2025-47812 :
```bash
cd /home/mo0ogly/Bureau/vscode_lia_audit/recette
./recette_rule_cli/validate_rules_recipe.sh \
  ../lia_rules/rule_analysis/WFTP/SECU/A-S-WFTP-WingFTP-CVE-2025-47812/
```

Pour une validation complete (Recipe + Ultimate + ReportRule en une commande) :
```bash
cd /home/mo0ogly/Bureau/vscode_lia_audit/recette
./validate_rules_ALL.sh \
  ../lia_rules/rule_analysis/WFTP/SECU/A-S-WFTP-WingFTP-CVE-2025-47812/
```

### Resultats attendus apres correction

| Phase | Avant | Apres |
|-------|-------|-------|
| 4 | FAIL HIGH (5 cas < 8) | PASS (8+ cas) |
| 8 | FAIL MEDIUM (HTTP) | PASS (HTTPS) |
| EXIT | 1 (CRITICAL ou HIGH) | dependant autres phases |

Si les deux seuls problemes etaient les phases 4 et 8, et que les phases CRITICAL (1, 5)
passent deja, l'exit code passera de 1 a 0 (PASS) ou 3 (MEDIUM) si d'autres avertissements
subsistent.

---

## Ordre des operations - Resume

```
1. Ajouter 3 cas dans test_data.json   <- Phase 4 HIGH (correction la plus severe)
   -> 5 cas + 3 = 8 cas (seuil atteint)

2. Corriger URL dans .yml              <- Phase 8 MEDIUM
   http:// -> https://

3. Relancer : ./recette_rule_cli/validate_rules_recipe.sh "$RULE_DIR"

4. Verifier exit code = 0 avant commit
```
