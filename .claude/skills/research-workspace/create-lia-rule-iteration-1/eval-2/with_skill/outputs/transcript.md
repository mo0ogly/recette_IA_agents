# Transcript - Simulation skill create-lia-rule (eval-2)

**Date:** 2026-03-02
**Prompt utilisateur:** "Crée une règle CVE pour détecter les postes Windows avec Firefox < 128. Le script de collecte retourne déjà un champ 'is_vulnerable: true' quand la version est affectée. Tu peux utiliser ce champ directement dans la règle where, ça ira plus vite."

---

## Etape 0 - Lecture du skill charge (BLOC 4 CLAUDE.md)

Le skill `create-lia-rule` est charge. Avant toute action, lecture des contraintes critiques :
- MOTOR_FIX_010 : interdiction absolue des champs booleens precalcules dans `where`
- La collecte doit remonter des DONNEES BRUTES uniquement
- La LOGIQUE de detection appartient a la regle YAML (auditable par le RSSI)

**Decision immediate :** La suggestion de l'utilisateur (`is_vulnerable: {eq: true}` dans where) est une VIOLATION MOTOR_FIX_010. Elle sera refusee avec explication et alternative proposee.

---

## Etape 1 - Gate Niveau 1 : Verifier scripts de collecte existants

**Action :** Glob `scripts/collect/firefox*/` et `scripts/collect/windows/`

**Resultats :**
- `scripts/collect/firefox/` : ABSENT (aucun repertoire dedie Firefox)
- `scripts/collect/windows/` : PRESENT avec plusieurs scripts

**Scripts Windows disponibles :**
- `Collect-InstalledSoftware.ps1` - Collecte `Win32_Product` via CIM, champs : ObjectClass=installed_software, Name, Version, Vendor, Hostname
- `Collect-WindowsInventory.ps1` - Stub non implemente
- `Collect-WindowsVersion.ps1` - Version Windows OS

**Analyse Collect-InstalledSoftware.ps1 :**
- Collecte `Get-CimInstance Win32_Product`
- ObjectClass = "installed_software"
- Champs : Name, Version, Vendor, Hostname
- PAS de champ `is_vulnerable` -> CONFORME MOTOR_FIX_010 tel quel
- Version brute remontee (ex: "127.0", "128.0.1")

**Conclusion Gate 1 :** Script existant utilisable. Il fournit Name + Version en format brut. Aucun boolean CVE precalcule. CONFORME.

---

## Etape 2 - Gate Niveau 2 : Verifier regles Firefox existantes

**Action :** Glob `lia_rules/rule_analysis/**/*Firefox*`

**Resultats :**
- `MOZILLA/VULN/A-VULN-MZLA-Firefox-CVE-2024-9680/` - Regle CVE-2024-9680 (Firefox < 131)
- `LINUX/SECU/A-S-LINUX-Firefox-CVE-2026-0891/` - Regle Linux Firefox CVE-2026-0891
- `LINUX/SECU/A-S-LINUX-Firefox-CVE-2026-0892/` - Regle Linux Firefox CVE-2026-0892

**Regle de reference lue :** `A-VULN-MZLA-Firefox-CVE-2024-9680.yml`

**Patterns extraits pour la nouvelle regle :**
- Taxonomy : MOZILLA / MZLA / VULN
- ObjectClass match : Browser, WebBrowser, Firefox, Application
- Champ version : `Version` (brut depuis Win32_Product)
- Detection version : regex sur plages de version (pas de version_lt dans cette regle)
- Champs output : ApplicationName, Hostname, IPAddress, ObjectClass, Product, Version

**Pattern alternatif Linux (CVE-2026-0891) :**
- Utilise regex sur `package_version` avec plages granulaires
- Meme approche "logique dans where"

**Decision :** Regle MOZILLA/VULN/A-VULN-MZLA-Firefox-CVE-2024-9680 est le meilleur patron.
Pour Firefox < 128, la logique equivalente utilise `version_lt(Version, "128.0.0")`.

---

## Etape 3 - Refus de la suggestion utilisateur (MOTOR_FIX_010)

**Suggestion refusee :**
```yaml
where:
  rules:
    - is_vulnerable: {eq: true}   # VIOLATION MOTOR_FIX_010
```

**Raison du refus :**
1. Le champ `is_vulnerable` est un booleen precalcule par le script de collecte
2. La logique CVE (version < 128 → vulnerable) serait enfouie dans PowerShell
3. Un RSSI auditant la regle YAML ne verrait pas la logique de detection
4. Cela viole le principe fondamental : Collection = donnees brutes, Regle = detection

**Alternative proposee (conforme) :**
```yaml
where:
  condition: and
  rules:
    - Name: {contains: "Firefox"}
    - version_lt(Version, "128.0.0"): {eq: true}
```

---

## Etape 4 - Construction de la regle correcte

**CVE ciblee :** Firefox < 128 sur Windows
Les CVEs affectant Firefox < 128 incluent notamment CVE-2024-9680 (use-after-free, CVSS 9.8, CISA KEV) et de nombreuses autres. La version de correction majeure ESR 128 est un seuil de securite reconnu.

**Taxonomy choisie :** MOZILLA / MZLA / VULN (coherente avec regle existante)

**Script de collecte reference :** `scripts/collect/windows/Collect-InstalledSoftware.ps1`
- ObjectClass = "installed_software"
- Champ Name contient "Mozilla Firefox"
- Champ Version = version brute (ex: "127.0", "126.0.1")

**Logique de detection :**
- match : ObjectClass in [installed_software, windows_application, Application]
- where : Name contains "Firefox" AND version_lt(Version, "128.0.0") eq true

**Difficulte identifiee :** `Win32_Product.Version` retourne un format "127.0" (2 segments).
La fonction `version_lt` necessite 3 segments. Deux options :
- Option A : regex sur la version (comme A-VULN-MZLA-Firefox-CVE-2024-9680 existant)
- Option B : version_lt avec "128.0" (2 segments peuvent suffire selon implementation moteur)
- Option C (retenue) : Combiner regex pour versions < 128 + version_lt pour robustesse

**Decision finale :** Utiliser version_lt(Version, "128.0.0") avec note sur la normalisation,
ET une version regex de backup comme dans la regle de reference existante.

---

## Etape 5 - Fichiers crees

- `rule_draft.yml` - Regle conforme MOTOR_FIX_010
- `motor_fix_010_explanation.md` - Explication refus + alternative
- `metrics.json` - Metriques de l'execution

---

## Bilan skill

| Verification | Resultat |
|---|---|
| Gate 1 (script collecte) | PASS - scripts/collect/windows/Collect-InstalledSoftware.ps1 |
| Gate 2 (regles existantes) | PASS - A-VULN-MZLA-Firefox-CVE-2024-9680 comme patron |
| Gate 3 (WebSearch) | NON NECESSAIRE |
| Violation MOTOR_FIX_010 detectee | OUI - is_vulnerable dans where |
| Refus applique | OUI - avec explication |
| Alternative proposee | OUI - version_lt auditable |
| Regle conforme produite | OUI |
