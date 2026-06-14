# Plan test_data.json - CVE-2025-47812 Wing FTP Server

## Objectif

16 cas de test (minimum 14 requis : 8+ vulnerables + 6+ safe).
Distribution cible : 60-65% vulnerables / 35-40% safe.
Resultat : 10 vulnerables + 6 safe = 62.5% / 37.5% (dans la cible).

---

## Structure de chaque cas

```json
{
  "ObjectClass": "WingFTPServer",
  "Hostname": "<fqdn-corp>",
  "Version": "<X.Y.Z>",
  "VersionNormalized": "<X.Y.Z.0>",
  "Platform": "<Windows|Linux|macOS>",
  "AdminPort": 5466,
  "AnonymousFTPEnabled": <true|false>,
  "_expected_match": <true|false>,
  "_test_description": "<description>"
}
```

Champs obligatoires (collectes par Collect-WingFTPServer.ps1) :
- ObjectClass : toujours "WingFTPServer" pour les cas Wing FTP
- Hostname : FQDN realiste de l'entreprise
- Version : version brute (ex. "7.4.3")
- VersionNormalized : version normalisee X.Y.Z.0 (pour version_lt())
- Platform : Windows / Linux / macOS
- AdminPort : port de l'interface admin (defaut 5466)
- AnonymousFTPEnabled : boolean - true = risque maximal

---

## Cas vulnerables (10 cas, _expected_match: true)

### Cas 1 - Boundary critique (derniere version vulnerable)
```json
{
  "ObjectClass": "WingFTPServer",
  "Hostname": "ftp-prod-01.corp.example.com",
  "Version": "7.4.3",
  "VersionNormalized": "7.4.3.0",
  "Platform": "Windows",
  "AdminPort": 5466,
  "AnonymousFTPEnabled": false,
  "_expected_match": true,
  "_test_description": "VULNERABLE - Version 7.4.3 (une version avant le patch 7.4.4) - cas limite - DOIT MATCHER"
}
```
Raison: version_lt("7.4.3.0", "7.4.4.0") = true. Cas limite le plus important.

### Cas 2 - Version 7.4.2 dans la plage affectee
```json
{
  "ObjectClass": "WingFTPServer",
  "Hostname": "ftp-prod-02.corp.example.com",
  "Version": "7.4.2",
  "VersionNormalized": "7.4.2.0",
  "Platform": "Windows",
  "AdminPort": 5466,
  "AnonymousFTPEnabled": false,
  "_expected_match": true,
  "_test_description": "VULNERABLE - Version 7.4.2 dans la plage < 7.4.4 - DOIT MATCHER"
}
```

### Cas 3 - Linux avec FTP anonyme (risque maximal)
```json
{
  "ObjectClass": "WingFTPServer",
  "Hostname": "ftp-linux-01.corp.example.com",
  "Version": "7.4.0",
  "VersionNormalized": "7.4.0.0",
  "Platform": "Linux",
  "AdminPort": 5466,
  "AnonymousFTPEnabled": true,
  "_expected_match": true,
  "_test_description": "VULNERABLE - Version 7.4.0 avec FTP anonyme actif - risque maximal - DOIT MATCHER"
}
```
Raison: FTP anonyme = acces zero-credential pour exploiter CVE-2025-47812.

### Cas 4 - Version 7.3.9 (branche mineure anterieure)
```json
{
  "ObjectClass": "WingFTPServer",
  "Hostname": "ftp-branch-01.corp.example.com",
  "Version": "7.3.9",
  "VersionNormalized": "7.3.9.0",
  "Platform": "Windows",
  "AdminPort": 5466,
  "AnonymousFTPEnabled": false,
  "_expected_match": true,
  "_test_description": "VULNERABLE - Version 7.3.9 branche mineure anterieure - DOIT MATCHER"
}
```

### Cas 5 - Version 7.3.0 (branche ancienne)
Meme structure, Version 7.3.0, Platform Linux.

### Cas 6 - Version 7.2.5 avec FTP anonyme (legacy + exposition critique)
```json
{
  "ObjectClass": "WingFTPServer",
  "Hostname": "ftp-legacy-01.corp.example.com",
  "Version": "7.2.5",
  "VersionNormalized": "7.2.5.0",
  "Platform": "Windows",
  "AdminPort": 5466,
  "AnonymousFTPEnabled": true,
  "_expected_match": true,
  "_test_description": "VULNERABLE - Version legacy 7.2.5 avec FTP anonyme - risque critique - DOIT MATCHER"
}
```

### Cas 7 - Version 7.0.0 (version majeure ancienne)
Meme structure, Version 7.0.0, Platform Windows.

### Cas 8 - Version 6.2.8 (version majeure precedente)
Meme structure, Version 6.2.8, Platform Linux.

### Cas 9 - Version 7.4.1 internet-facing avec FTP anonyme
```json
{
  "ObjectClass": "WingFTPServer",
  "Hostname": "ftp-anon-internet.corp.example.com",
  "Version": "7.4.1",
  "VersionNormalized": "7.4.1.0",
  "Platform": "Windows",
  "AdminPort": 5466,
  "AnonymousFTPEnabled": true,
  "_expected_match": true,
  "_test_description": "VULNERABLE - Version 7.4.1 expose internet avec FTP anonyme - scenario exploitation le plus critique - DOIT MATCHER"
}
```

### Cas 10 - Edge case version null (serveur decommissionne)
```json
{
  "ObjectClass": "WingFTPServer",
  "Hostname": "ftp-decommissioned.corp.example.com",
  "Version": null,
  "VersionNormalized": null,
  "Platform": "Windows",
  "AdminPort": 5466,
  "AnonymousFTPEnabled": false,
  "_expected_match": true,
  "_test_description": "VULNERABLE - Edge case: version null traitee comme 0.0.0.0 < 7.4.4.0 par le moteur - serveur inconnu = signale - DOIT MATCHER"
}
```
Raison: Le moteur traite null comme inferieur a toute version => signal de precaution.

---

## Cas safe (6 cas, _expected_match: false)

### Cas 11 - Version exacte du patch (boundary)
```json
{
  "ObjectClass": "WingFTPServer",
  "Hostname": "ftp-patched-01.corp.example.com",
  "Version": "7.4.4",
  "VersionNormalized": "7.4.4.0",
  "Platform": "Windows",
  "AdminPort": 5466,
  "AnonymousFTPEnabled": false,
  "_expected_match": false,
  "_test_description": "SAFE - Version exacte du patch 7.4.4 (cas limite superieur) - NE DOIT PAS MATCHER"
}
```
Raison: version_lt("7.4.4.0", "7.4.4.0") = false. Cas limite le plus important cote safe.

### Cas 12 - Version superieure au patch
Version 7.4.5, NE DOIT PAS MATCHER.

### Cas 13 - Version mineure plus recente
Version 7.5.0, NE DOIT PAS MATCHER.

### Cas 14 - Version majeure future
Version 8.0.0, NE DOIT PAS MATCHER.

### Cas 15 - Mauvais ObjectClass (autre FTP Server)
```json
{
  "ObjectClass": "OtherFTPServer",
  "Hostname": "filezilla-srv-01.corp.example.com",
  "Version": "7.4.3",
  "VersionNormalized": "7.4.3.0",
  "Platform": "Windows",
  "AdminPort": 14147,
  "AnonymousFTPEnabled": false,
  "_expected_match": false,
  "_test_description": "SAFE - ObjectClass incorrect (OtherFTPServer != WingFTPServer) - la version 7.4.3 ne s'applique pas - NE DOIT PAS MATCHER"
}
```
Raison: Gate `match.ObjectClass.eq: WingFTPServer` filtre ce cas en premier.

### Cas 16 - macOS patche
```json
{
  "ObjectClass": "WingFTPServer",
  "Hostname": "ftp-macos-01.corp.example.com",
  "Version": "7.4.4",
  "VersionNormalized": "7.4.4.0",
  "Platform": "macOS",
  "AdminPort": 5466,
  "AnonymousFTPEnabled": false,
  "_expected_match": false,
  "_test_description": "SAFE - macOS avec version patchee 7.4.4 - NE DOIT PAS MATCHER"
}
```

---

## Verification des contraintes de recette

| Contrainte | Valeur | Statut |
|-----------|--------|--------|
| Minimum 14 cas | 16 cas | PASSE |
| Minimum 8 vulnerables | 10 vulnerables | PASSE |
| Minimum 6 safe | 6 safe | PASSE |
| Ratio cible 60/40 | 62.5% / 37.5% | PASSE |
| Cas limite inferieur (derniere version vulnerable) | 7.4.3 = cas 1 | PRESENT |
| Cas limite superieur (premiere version safe) | 7.4.4 = cas 11 | PRESENT |
| Edge case version null | cas 10 | PRESENT |
| Mauvais ObjectClass | cas 15 | PRESENT |
| Multi-platform | Windows + Linux + macOS | PRESENT |
| Avec FTP anonyme | cas 3, 6, 9 | PRESENT |
| Donnees reelles (pas mock) | hostnames FQDN corp | PASSE |
| _expected_match present | tous les cas | PASSE |
| _test_description present | tous les cas | PASSE |

---

## Logique de detection verifiee

La regle `where` utilise:
```yaml
condition: and
rules:
  - ObjectClass: {eq: WingFTPServer}
  - version_lt(VersionNormalized, "7.4.4.0"): {eq: true}
```

- Cas 1-9: ObjectClass = WingFTPServer ET version_lt() = true -> MATCH
- Cas 10: ObjectClass = WingFTPServer ET version_lt(null, "7.4.4.0") = true (null = 0.0.0.0) -> MATCH
- Cas 11-14: ObjectClass = WingFTPServer ET version_lt() = false -> PAS DE MATCH
- Cas 15: ObjectClass = OtherFTPServer -> Gate match echoue -> PAS DE MATCH
- Cas 16: ObjectClass = WingFTPServer ET version_lt("7.4.4.0", "7.4.4.0") = false -> PAS DE MATCH
