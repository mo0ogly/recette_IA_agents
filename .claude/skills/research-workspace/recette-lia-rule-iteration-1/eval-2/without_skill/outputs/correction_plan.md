# Plan de correction - EXIT=1 CRITICAL recette

## Contexte

La recette `validate_rules_recipe.sh` retourne EXIT=1 CRITICAL sur deux problemes distincts.
Les deux doivent etre corriges avant tout commit.

---

## CORRECTION 1 - Phase 8 : URL HTTP non securisee (A FAIRE EN PREMIER)

### Pourquoi en premier

La Phase 8 check 8.3 est un `check_critical` dans le validateur. Une seule URL HTTP suffit
a declencher EXIT=1. C'est la correction la plus rapide (1 ligne a modifier) et elle doit
etre faite avant d'engager du temps sur Phase 4.

### Probleme exact

Dans la section `references:` du fichier YAML, une URL commence par `http://` au lieu de `https://`.

URL incorrecte :
```
http://nvd.nist.gov/vuln/detail/CVE-2025-47812
```

URL correcte :
```
https://nvd.nist.gov/vuln/detail/CVE-2025-47812
```

### Action

Ouvrir le fichier YAML de la regle et remplacer exactement cette chaine dans la section references :

```yaml
# Avant
  - "http://nvd.nist.gov/vuln/detail/CVE-2025-47812"

# Apres
  - "https://nvd.nist.gov/vuln/detail/CVE-2025-47812"
```

Verification apres correction :
```bash
grep 'http://' chemin/vers/la/regle.yml
# Doit retourner vide (aucun resultat)
```

---

## CORRECTION 2 - Phase 4 : Nombre de cas de test insuffisant (A FAIRE EN SECOND)

### Probleme exact

Le fichier `test_data.json` contient 5 cas. Le validateur Phase 4 check 4.2 exige un minimum
(>= 8 selon le prompt, >= 10 selon le code actuel de phase04_test_data_quality.sh ligne 32).
Le seuil exact dependra de la version du script en place, mais dans tous les cas il faut
atteindre le minimum requis.

### Strategie d'ajout

La regle CVE-2025-47812 concerne Wing FTP Server (versions < 7.4.4 vulnerables).
Avec 5 cas existants, il faut en ajouter au minimum 3 (pour atteindre 8) ou 5 (pour 10).

Distribution recommandee (ratio 55-65% vulnerables) :
- 8 cas minimum : 5 vulnerables (_expected_match: true) + 3 safe (_expected_match: false)
- 10 cas recommandes : 6 vulnerables + 4 safe

### Cas a ajouter (exemples concrets pour CVE-2025-47812)

Cas vulnerables supplementaires (`_expected_match: true`) :

```json
{
  "ObjectClass": "WingFTPServer",
  "Hostname": "ftp-backup-01.acme-corp.eu",
  "Version": "7.1.0",
  "VersionNormalized": "7.1.0.0",
  "Platform": "Windows",
  "AdminPort": 5466,
  "AnonymousFTPEnabled": false,
  "_expected_match": true,
  "_test_description": "VULNERABLE - Version 7.1.0 older minor branch - MUST MATCH"
},
{
  "ObjectClass": "WingFTPServer",
  "Hostname": "ftp-dmz-01.acme-corp.eu",
  "Version": "7.4.1",
  "VersionNormalized": "7.4.1.0",
  "Platform": "Linux",
  "AdminPort": 5466,
  "AnonymousFTPEnabled": true,
  "_expected_match": true,
  "_test_description": "VULNERABLE - Version 7.4.1 with anonymous FTP on Linux - MUST MATCH"
}
```

Cas safe supplementaires (`_expected_match: false`) :

```json
{
  "ObjectClass": "WingFTPServer",
  "Hostname": "ftp-patched-dc01.acme-corp.eu",
  "Version": "7.4.4",
  "VersionNormalized": "7.4.4.0",
  "Platform": "Windows",
  "AdminPort": 5466,
  "AnonymousFTPEnabled": false,
  "_expected_match": false,
  "_test_description": "SAFE - Exact fixed version 7.4.4 boundary - MUST NOT MATCH"
},
{
  "ObjectClass": "OtherFTPServer",
  "Hostname": "filezilla-srv-02.acme-corp.eu",
  "Version": "7.4.3",
  "VersionNormalized": "7.4.3.0",
  "Platform": "Windows",
  "AdminPort": 14147,
  "AnonymousFTPEnabled": false,
  "_expected_match": false,
  "_test_description": "SAFE - Wrong ObjectClass (OtherFTPServer) - MUST NOT MATCH"
}
```

### Points d'attention lors de l'ajout

1. Utiliser des noms de domaine diversifies (pas tous `.corp.example.com` -> Phase 4 check 4.9 homogeneite)
2. Ne pas utiliser `example.com`, `corp.local`, `contoso.com` -> Phase 4 check 4.5 fake domains
3. Documenter chaque cas avec `_test_description`
4. Respecter la distribution 55-65% vulnerables (check Phase 12 ratio)
5. Les descriptions des cas SAFE ne doivent pas contenir les mots "CVE-XXXX", "CRITICAL", "VULNERABLE" -> Phase 4 check 4.12

---

## Verification finale

Apres les deux corrections, relancer la recette complete :

```bash
cd /home/mo0ogly/Bureau/vscode_lia_audit/recette
./validate_rules_recipe.sh ../lia_rules/rule_analysis/WFTP/SECU/A-S-WFTP-WingFTP-CVE-2025-47812/
```

Attendu : EXIT=0 (ou au minimum plus de EXIT=1 CRITICAL sur Phase 4 et Phase 8).

Si d'autres phases echouent, les corriger avant commit. Le commit n'est autorise que si
les 3 validateurs passent (recipe + ultimate + reportrule).

---

## Ordre de priorite justifie

| Ordre | Phase | Severite | Temps correction | Justification |
|-------|-------|----------|-----------------|---------------|
| 1 | Phase 8 (URL HTTP) | CRITICAL | < 1 minute | 1 caractere a changer, bloque EXIT=1 |
| 2 | Phase 4 (cas tests) | HIGH/CRITICAL | 10-15 minutes | Ajout de donnees, necessite reflexion |
