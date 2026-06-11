# Catalogue de Corrections - Validation LIA-Scan

Reference rapide des corrections pour chaque type d'erreur detectee par la recette.

---

## CRITICAL - Corrections Obligatoires

### 1. Fichiers manquants (Phase 1)

**Erreur:** `CRITICAL: Missing required file: test_data.json`

**Correction:** Creer le fichier manquant selon le template.

```bash
# Fichiers obligatoires dans un repertoire de regle:
A-RULE-NAME.yml         # Regle YAML
test_data.json          # Donnees de test (>= 8 cas)
test_rule.sh            # Script test moteur (chmod +x)
```

Fichiers recommandes:
```bash
R-A-RULE-NAME.json      # ReportRule JSON (remediation)
RESEARCH_EVIDENCE.md    # Sources et recherche
```

### 2. MOTOR_FIX_010 violation (where clause)

**Erreur:** `CRITICAL: MOTOR_FIX_010 violation - is_compliant found in where clause`

**Correction:**
```yaml
# AVANT (VIOLATION)
where:
  rules:
    - is_compliant: {eq: false}
    - CVE_2025_1234_is_vulnerable: {eq: true}

# APRES (CONFORME)
where:
  condition: and
  rules:
    - version_lt(Version, "12.8.0.0"): {eq: true}
    # Ou pour compliance:
    - usb_ports_enabled: {eq: true}
    - usb_justification: {eq: ""}
```

### 3. object_type_field manquant

**Erreur:** `CRITICAL: Missing required field: object_type_field`

**Correction:** Ajouter apres le champ `target`:
```yaml
target: BANK
object_type_field: ObjectClass
```

### 4. Execution moteur echoue (Phase 5)

**Erreur:** `CRITICAL: Engine execution failed`

**Diagnostics:**
```bash
# Verifier syntaxe YAML
python3 -c "import yaml; yaml.safe_load(open('RULE.yml'))"

# Verifier syntaxe JSON test_data
python3 -m json.tool test_data.json > /dev/null

# Executer manuellement avec debug
ENGINE="/home/mo0ogly/Bureau/vscode_lia_audit/bin/lia_scan_engine"
$ENGINE -multi -rules . -events test_data.json -quadrigramme TEST -date $(date +%Y%m%d) 2>&1
```

**Causes frequentes:**
- Syntaxe YAML invalide (indentation, quotes)
- Champ dans where clause inexistant dans test_data
- Fonction inconnue dans computed field
- Version operator avec < 3 segments

### 5. Taxonomy directory coherence (Phase 14)

**Erreur:** `CRITICAL: Taxonomy mismatch - directory BANK but taxonomy says ADDS`

**Correction:** Aligner la section taxonomy avec le repertoire:
```yaml
# Si la regle est dans lia_rules/rule_analysis/BANK/SECU/TPSE/
taxonomy:
  taxonomy: BANK           # Doit matcher le premier niveau
  taxonomy_short: BANK
  axis: security
  axis_short: SECU         # Doit matcher le deuxieme niveau
  block: Terminal Security
  block_short: TPSE        # Doit matcher le troisieme niveau
```

**Mismatches connus (valides):**
| Repertoire | taxonomy_short | Raison |
|------------|---------------|--------|
| ALIBABA | ALIC | Abbreviation 4 chars |
| AWS | AWSC | Disambiguation |
| CITRIX | CITR | Abbreviation |
| IBM | IBMC | Disambiguation |
| ORACLE | ORCL | Abbreviation |
| VMWARE | VMWA | Abbreviation |

---

## HIGH - Corrections Recommandees

### 6. Computed fields manquants (MOTOR_FIX_003)

**Erreur:** `HIGH: Missing computed field: DetectionLogic`

**Correction:** Ajouter les 5 computed fields obligatoires:
```yaml
output:
  computed:
    Severity: "if(condition, 'CRITICAL', 'MEDIUM')"
    RiskReason: "if(condition, 'Description risque', 'Conforme')"
    RecommendedAction: "if(condition, 'Action corrective', 'Aucune')"
    DetectionLogic: "if(condition, 'Description logique detection', 'N/A')"
    ComplianceImpact: "if(condition, 'Impact conformite', 'Conforme')"
```

**Rappel:** Toute string statique doit etre wrappee dans `if()`:
```yaml
# ERREUR
DetectionLogic: "Checks version against threshold"
# CORRECT
DetectionLogic: "if(Version != '', 'Checks version against threshold', 'N/A')"
```

### 7. Compliance mapping uppercase

**Erreur:** `HIGH: Compliance key 'ANSSI' must be lowercase`

**Correction:**
```yaml
# AVANT
compliance_mapping:
  ANSSI:
    - id: "R14"
  PCI_DSS:
    - id: "6.2"
  ISO_27001:
    - id: "A.12.6.1"

# APRES
compliance_mapping:
  anssi:
    - id: "R14"
  pci_dss:
    - id: "6.2"
  iso_27001:
    - id: "A.12.6.1"
```

### 8. output.include au lieu de output.fields (FORMAT V2)

**Erreur:** `HIGH: Using deprecated output.include - use output.fields`

**Correction:**
```yaml
# AVANT (ancien format)
output:
  include:
    - Hostname
    - Version

# APRES (FORMAT V2)
output:
  fields:
    Hostname: Hostname
    Version: Version
```

**IMPORTANT:** Pas de renommage dans output.fields:
```yaml
# ERREUR (peut donner null)
output:
  fields:
    Server_Name: Hostname

# CORRECT
output:
  fields:
    Hostname: Hostname
```

### 9. data_source incomplete

**Erreur:** `HIGH: data_source missing required field: collection_script`

**Correction:**
```yaml
data_source:
  collection_script: "scripts/collect/{tech}/Collect-{Tech}.ps1"
  description: "Description des donnees collectees"
  collection_method: "PowerShell Script"
  type: collection
  collection_type: "STANDARD"
  required_fields:
    - ObjectClass
    - Hostname
    - Version
```

### 9bis. COLLECTION_SCRIPT_NOT_FOUND (cross_references CRITICAL)

**Erreur:** `Collection script not found: Collect-XXX.ps1` (validate_cross_references).

**Ou vivent les collecteurs AD (verifie 2026-05-29):**
- Canonique (cherche par le validateur, recursif par basename): `scripts/collect/active_directory/` (~62 collecteurs `Collect-*.ps1` + master `Collect-ADCompleteTaxonomy.ps1`).
- Source PingCastle (NON cherchee par le validateur): `pingcastle_conversion/scripts/<topic>/Collect-*.ps1` et `pingcastle_conversion/_rules_ad/<RULE>/Collect-*.ps1`. Beaucoup de collecteurs "manquants" y existent (ex `Collect-RODCDeniedGroupMissing.ps1`, `Collect-Owner.ps1`, `Collect-TrustsAccounts.ps1`, `Collect-SysvolNTFRS.ps1`, `Collect-SIDHistoryDangerous.ps1`).

**Mapping autoritaire ObjectClass -> collecteur:** `scripts/collect/active_directory/COLLECTORS_MAPPING.md` (+ `COLLECTORS_INDEX.md`). Le lien regle<->script se fait par `ObjectClass` (le collecteur emet un ObjectClass, la regle filtre dessus), PAS par nom de fichier.

**Correction (R4 -- zero fabrication):**
1. Lire l'ObjectClass du `match` de la regle.
2. `grep -rl "ObjectClass.*<class>" scripts/collect/active_directory/*.ps1` pour trouver le collecteur qui l'emet.
3. Si absent de `scripts/collect/` mais present dans `pingcastle_conversion/` -> reprendre/promouvoir ce script (le vrai existe, mauvais dossier).
4. Aligner `data_source.collection_script` (basename) + `script_location` sur le collecteur reel verifie. Verifier qu'il emet le `required_files.pattern`.
5. JAMAIS inventer un collecteur. Le master `Collect-ADCompleteTaxonomy.ps1` produit la taxonomy complete (test XML `TEST_AD_COMPLETE_TAXONOMY.xml`).

**Note structure (struct-2 defect, 2026-05-29):** ~93 regles ADDS placent leurs computed fields (Severity, RiskReason, DetectionLogic...) sous `output.fields:` au lieu de `output.computed:`. Le moteur les IGNORE (computed absents de l'output, severite UNKNOWN). Fix = wrapper sous `output.computed:`. Verifier output moteur avant/apres (R26).

### 10. Test data insuffisant (Phase 4)

**Erreur:** `HIGH: Only 5 test cases (minimum 8 required)`

**Correction:** Ajouter des cas dans test_data.json:
- Minimum 8 cas (idealement 14+)
- 55-65% vulnerables (`_expected_match: true`)
- 35-45% securises (`_expected_match: false`)
- 2+ edge cases (decommissioned, null, inactive)

Chaque cas doit avoir:
```json
{
  "ObjectClass": "...",
  "_expected_match": true,
  "Description": "VULNERABLE - Raison explicite"
}
```

### 11. Faux positifs/negatifs detectes (Phase 6)

**Erreur:** `HIGH: False positive detected - safe case matched`

**Diagnostics:**
1. Executer `./test_rule.sh` et noter les matches
2. Comparer avec `_expected_match` dans test_data.json
3. Identifier quel cas est mal classifie

**Corrections possibles:**
- Affiner la where clause (ajouter condition supplementaire)
- Corriger `_expected_match` dans test_data.json si le flag est faux
- Ajouter une exclusion (status != "decommissioned")

### 12. References placeholder

**Erreur:** `HIGH: Reference URL is placeholder: https://example.com`

**Correction:** Remplacer par des URLs reelles:
```yaml
references:
  - "https://nvd.nist.gov/vuln/detail/CVE-YYYY-XXXXX"
  - "https://www.cisa.gov/known-exploited-vulnerabilities-catalog"
  - "https://vendor.com/security-advisory/SA-XXXXX"
```

---

## MEDIUM - Corrections Optionnelles

### 13. Tags insuffisants

**Erreur:** `MEDIUM: Only 2 tags (minimum 3 recommended)`

**Correction:** Ajouter des tags pertinents:
```yaml
tags:
  - banking
  - terminal
  - pci-pts
  - payment-terminal
  - physical-security
```

### 14. Test data ratio desequilibre

**Erreur:** `MEDIUM: Vulnerable ratio 80% exceeds target 65%`

**Correction:** Ajouter plus de cas securises pour equilibrer le ratio.

### 15. Metadata manquante

**Erreur:** `MEDIUM: Missing metadata.date`

**Correction:**
```yaml
metadata:
  author: "LIA-Scan Rules Team"
  date: "2026-02-15"
  version: "1.0"
  category: "Terminal Security"
```

### 16. taxonomy manquant technology/category

**Erreur:** `MEDIUM: Missing taxonomy.technology`

**Correction:**
```yaml
taxonomy:
  taxonomy: DOCKER
  taxonomy_short: DOCK
  technology: "Docker Engine"      # Ajouter
  category: "Container Security"   # Ajouter
```

### 17. Version comparison sans 3 segments

**Erreur:** `MEDIUM: Version string "16.10" should have 3 segments`

**Correction:**
```yaml
# AVANT
- Version: {version_lt: "16.10"}

# APRES
- Version: {version_lt: "16.10.0"}
```

### 18. ReportRule - compliance_references incomplete

**Erreur:** `MEDIUM: ReportRule missing pci_dss requirement field`

**Correction:**
```json
"compliance_references": {
  "pci_dss": [
    {
      "id": "6.3.3",
      "title": "Security patches",
      "requirement": "Install security patches within defined timeframe",
      "version": "v4.0"
    }
  ]
}
```

### 19. ReportRule - metadata manquante

**Erreur:** `MEDIUM: ReportRule missing author, date`

**Correction:** Ajouter au JSON:
```json
{
  "rule_id": "A-RULE-NAME",
  "author": "LIA-Scan Rules Team",
  "date": "2026-02-15",
  "category": "Terminal Security",
  "risk_level": "high",
  "risk_score": 75
}
```

### 20. Commentaires SAFE contenant "CVE-" (faux positif ratio)

**Erreur:** `HIGH: Vulnerable cases ratio 75% exceeds target 70%`
alors que le compte des `_expected_match: false` est correct.

**Cause:** Le validateur ratio detecte les mots-cles `CVE|CRITICAL|HIGH|Vulnerable|Affected`
dans le champ `comment` / `Description` pour classifier les cas, independamment du flag
`_expected_match`. Un cas SAFE avec "CVE-2025-XXXXX" dans son commentaire est compte VULNERABLE.

**Correction:** Dans les cas SAFE, remplacer toute reference au CVE dans le commentaire:
```json
// AVANT (compte comme VULNERABLE a cause de "CVE-2025-27151")
{
  "_expected_match": false,
  "comment": "SAFE - Patched - Redis 6.2.x is below minimum version for CVE-2025-27151"
}

// APRES (compte correctement comme SAFE)
{
  "_expected_match": false,
  "comment": "SAFE - Patched - Redis 6.2.x is below minimum affected version - not impacted"
}
```

**Regle:** Dans les descriptions de cas SAFE, ne jamais mentionner le CVE ID, "CRITICAL" ou "HIGH".
Utiliser des formulations neutres: "not impacted", "patched", "below minimum affected version".

---

### 21. block_short absent de la taxonomie

**Erreur:** `CRITICAL: Block 'CVEP' not found in axis 'VULN' of taxonomy 'VEEAM'`

**Cause:** La valeur `block_short` dans le YAML fait reference a un block qui n'existe pas
dans le fichier `config/taxonomy/{TECH}_taxonomy.json`.

**Correction en 2 etapes:**

**Etape 1 - Verifier les blocks disponibles:**
```bash
python3 -c "
import json, glob
for f in glob.glob('config/taxonomy/{TECH}*.json'):
    d = json.load(open(f))
    for tax in d.get('taxonomies', []):
        for axis in tax.get('axes', []):
            if axis.get('quadrigram') == 'VULN':
                print('VULN blocks:', [b.get('quadrigram') for b in axis.get('blocks', [])])
"
```

**Etape 2a - Si un block existant convient:** Utiliser son quadrigram dans le YAML:
```yaml
taxonomy:
  block: CVE Detection
  block_short: VULN   # Utiliser un block existant
```

**Etape 2b - Si aucun block ne convient:** Ajouter le block dans la taxonomie:
```python
# Ajouter dans le fichier config/taxonomy/{TECH}_taxonomy.json
# Dans l'axe VULN, section "blocks":
{"quadrigram": "VULN", "name": "CVE Detection", "description": "CVE vulnerability detection rules"}
```

**Pattern courant:** La plupart des taxonomies CVE utilisent `block_short: VULN` avec un block
nomme "CVE Detection" ou directement `block_short: CVEP` (CVE Patching) s'il existe.

---

### 22. Operateur |exists inefficace pour attributs AD optionnels absents

**Erreur:** La regle ne detecte pas les objets AD dont un attribut optionnel est absent (null JSON).

**Cause:** L'operateur `|exists` verifie si un champ est present dans le JSON, mais quand le script
PowerShell exporte un attribut AD absent, il est serialise comme `null` (la cle existe, la valeur est null).
L'operateur `|exists: eq: false` ne matche donc pas un champ null - il ne matche que les champs
absents du JSON.

**Exemple concret (LAPS-NotDeployed):**
```yaml
# AVANT - Ne detecte pas les workstations sans LAPS (attribut null, pas absent)
where:
  rules:
    - LAPSPwdExpirationTime|exists:
        eq: false    # ECHOUE: le champ existe avec valeur null

# APRES - Pattern correct avec isempty (implementee depuis v4.2)
where:
  condition: and
  rules:
    - ObjectClass:
        eq: "computer"
    - LAPSPwdExpirationTime:
        isempty: true    # CORRECT: detecte null ET "" (les deux cas AD)
```

**Pattern recommande pour attributs AD optionnels:**
```yaml
# Detecter "attribut non renseigne" - isempty est le pattern OFFICIEL
- AttributeName:
    isempty: true       # Detecte: null, "", et valeur absente

# Detecter "attribut renseigne"
- AttributeName:
    isnotempty: true    # Detecte: toute valeur non-nulle et non-vide

# Difference avec exists:
# exists: false  → clef absente du JSON (cas tres rare en export PowerShell)
# isempty: true  → clef presente mais null ou "" (cas standard AD)
```

**Attributs AD concernes par ce pattern:**
- `ms-Mcs-AdmPwdExpirationTime` (Legacy LAPS) → absent = null JSON
- `msLAPS-PasswordExpirationTime` (Windows LAPS) → absent = null JSON
- `servicePrincipalName` → absent = null ou tableau vide
- `msDS-AllowedToDelegateTo` → absent = null JSON
- `AdminCount` → absent = null (pas 0)
- `ManagedBy` → absent = null JSON

**Regle generale MISE A JOUR (2026-02-18):**

`isempty: true` seul ne suffit pas si les cles sont VRAIMENT ABSENTES du JSON.
En pratique, les exports PowerShell peuvent produire les deux representations.
Le pattern robuste combine les deux cas :

```yaml
# PATTERN DEFINITIF - attribut AD optionnel absent ou null
- condition: or
  rules:
    - AttributeName|exists:
        eq: false      # cle absente du JSON (cas test_data.json et certains exports)
    - AttributeName:
        isempty: true  # cle presente avec null ou "" (cas production PowerShell)
```

---

### 23. target: ADDS vs target: ActiveDirectory pour regles ADDS

**Erreur:** `[EXECUTION] Unknown target in rule: ADDS (not in platforms.json)`
**OU:** `[validate_cross_references] X taxonomy: ActiveDirectory_taxonomy.json - not found`

**Contexte:** Conflit entre le moteur et le validator Python V5 :
- `target: ActiveDirectory` → moteur OK, cross_references validator FAIL
- `target: ADDS` → moteur FAIL (si ADDS absent de platforms.json), cross_references PASS

**Correction:** Utiliser `target: ADDS` ET ajouter ADDS dans `config/platforms.json`

```json
// config/platforms.json - section "targets"
{
  "targets": {
    "ActiveDirectory": "ad",
    "ADDS": "ad"          // AJOUTER cette ligne
  }
}
```

```yaml
# Regle YAML ADDS
target: ADDS    # (pas ActiveDirectory)
```

**Status:** ADDS est desormais dans `config/platforms.json` (commit 2026-02-18).
Pour les futures regles ADDS, utiliser `target: ADDS` directement.

---

### 24. output.fields vs output.include (validator Python V5)

**Erreur:** `CRITICAL: output.fields detected - UNSUPPORTED FORMAT → Engine struct expects output.include`

**Contexte:** Le validator Python V5 `validate_rule_output_format.py` attend `output.include`
(ancien format). Le moteur Go et les guides recents disent `output.fields`.
Pour passer le ultimate validator (qui inclut V5 Python), utiliser `output.include`.

**Correction:**
```yaml
# AVANT - echoue au validator Python V5 (ultimate)
output:
  fields:
    ObjectClass: ObjectClass
    Hostname: Hostname

# APRES - valide pour tous les validators
output:
  include:
    ObjectClass: ObjectClass
    Hostname: Hostname
```

**Note:** Les computed fields restent dans `output.computed:` (section separee, non affectee).

---

### 25. Computed fields - pattern word( detecte comme appel de fonction

**Erreur:** `INVALID - Invalid operators/functions detected: endpoint(), populated(), installed()...`

**Contexte:** Le validator `validate_operators_functions.py` utilise le regex `([a-z_]+)\s*\(`
sur TOUT le contenu des computed fields, y compris les textes statiques entre guillemets.
Tout mot minuscule (ou avec underscore) suivi d'une parenthese est detecte comme fonction.

**Exemples de patterns pieges:**
```
"...on endpoint (gpupdate..."      → detecte endpoint()
"...attribute populated (Get-AD..."  → detecte populated()
"...CSE installed (Get-Item..."    → detecte installed()
"ANSSI_vuln_laps_installed (Level" → detecte _vuln_laps_installed()
"ExpirationTime (Windows LAPS)"    → detecte ime()
```

**Correction:** Rephrase les textes pour eviter `mot(` ou `mot (` :
```yaml
# AVANT - piege le validator
RecommendedAction: "if(cond, '...update on endpoint (gpupdate /force)...', '')"

# APRES - sans parenthese apres un mot minuscule
RecommendedAction: "if(cond, '...run gpupdate /force to update endpoint policies...', '')"
```

**Regles de protection:**
- Ne jamais ecrire `nom_de_fonction (` dans les valeurs de champs computed
- Remplacer `word (...)` par `word: ...` ou reformuler sans parentheses
- Les acronymes en majuscules ne posent pas de probleme (ex: `LAPS (Local Admin)` → OK car L en majuscule)
- Les underscores dans les textes statiques peuvent declencher le pattern si suivis de `(`

---

### 26. Champ _test_description mal nommé (Phase 12 - ratio vulnérables)

**Erreur:** `HIGH: Only 0 vulnerable test cases out of 15 (expected 8-9)`
Tous les cas VULNERABLE passent à 0 malgré `_expected_match: true`.

**Cause:** Phase 12 lit uniquement `._test_description`. Si le champ est nommé différemment
(`_case_description`, `_description`, `comment`, `Description`), le validateur ne trouve aucun cas
et renvoie 0% de vulnérables.

**Champ autorisé (un seul) :** `_test_description`

**Correction:**
```json
// INTERDIT - Phase 12 ne lit pas ces champs
{"_case_description": "VULNERABLE - Module not loaded"}
{"_description": "VULNERABLE - AppArmor disabled"}
{"comment": "VULNERABLE - No enforce profiles"}

// CORRECT - Phase 12 lit _test_description
{"_test_description": "VULNERABLE - Module not loaded"}
{"_test_description": "SAFE: AppArmor enabled with enforce profiles active"}
```

**Regle de prevention:** Dans tout nouveau test_data.json, utiliser SYSTEMATIQUEMENT
`_test_description` comme nom de champ pour les descriptions de cas de test.

---

### 27. Prefix descriptions VULNERABLE incorrect (Phase 12 - startswith)

**Erreur:** `HIGH: Vulnerable ratio 0% - expected 55-65%`
Meme avec `_test_description` present, Phase 12 renvoie 0 cas vulnérables.

**Cause:** Phase 12 utilise `ascii_upcase | startswith("VULNERABLE")` sur `_test_description`.
Les prefixes alternatifs sont silencieusement ignorés et comptés comme 0.

**Prefixes REJETÉS (comptés comme non-vulnérables) :**
```
"DETECTED:"
"DETECTED CRITICAL:"
"NOT_PROTECTED:"
"MISCONFIGURED:"
"ALERT:"
"IMPACTED:"
```

**Prefix OBLIGATOIRE pour cas vulnérables :** `VULNERABLE` (ou `VULNERABLE -`)

**Correction:**
```json
// INTERDIT - Phase 12 compte 0 vulnérables
{"_test_description": "DETECTED: Module not loaded - AppArmor absent"}
{"_test_description": "NOT_PROTECTED: AppArmor disabled at boot"}
{"_test_description": "DETECTED CRITICAL: All profiles in complain mode"}

// CORRECT - Phase 12 compte comme vulnérable
{"_test_description": "VULNERABLE - Module not loaded (apparmor_module_loaded=false)"}
{"_test_description": "VULNERABLE - AppArmor disabled at runtime (apparmor_enabled=false)"}
{"_test_description": "VULNERABLE - AppArmor enabled but 0 enforce profiles - complain mode only"}
```

**Prefixes acceptés pour cas SAFE (Phase 12) :** `SAFE`, `PATCHED`, `NOT_VULNERABLE`, `NOT_APPLICABLE`

---

### 28. Domaines non reconnus dans references (Phase 6 - officialité)

**Erreur:** `HIGH: Only 1 official reference domain found (minimum 2 required)`
Malgré plusieurs URLs dans `references:`, le check échoue.

**Cause:** Phase 6 maintient une liste stricte de domaines reconnus comme "officiels".
`qualys.com`, `blog.qualys.com`, `ubuntu.com` et les blogs éditeurs NE SONT PAS dans cette liste.

**Domaines officiels reconnus par Phase 6 :**
```
nvd.nist.gov
cisa.gov
attack.mitre.org
csrc.nist.gov
ssi.gouv.fr (ANSSI)
cisecurity.org
pcisecuritystandards.org
emvco.com
iso.org
```

**Correction :** Remplacer les URLs vendor/blog par des URLs officielles :
```yaml
# AVANT - Phase 6 compte 1 officiel (seulement nvd.nist.gov)
references:
  - https://nvd.nist.gov/vuln/detail/CVE-2026-23268
  - https://blog.qualys.com/vulnerabilities-threat-research/crackarmor
  - https://ubuntu.com/security/CVE-2026-23268

# APRES - Phase 6 compte 2+ officiels
references:
  - https://nvd.nist.gov/vuln/detail/CVE-2026-23268
  - https://attack.mitre.org/techniques/T1548/
  - https://www.cisecurity.org/cis-benchmarks/
  - https://ubuntu.com/security/CVE-2026-23268
```

**Strategie :** Pour toute nouvelle regle, inclure SYSTEMATIQUEMENT au moins :
- `nvd.nist.gov/vuln/detail/{CVE_ID}` (si regle CVE)
- `attack.mitre.org/techniques/TXXXX/` (MITRE ATT&CK)
Ces deux URLs garantissent le minimum de 2 domaines officiels.

---

## Erreurs frequentes capitalisees (ex-SKILL.md v2)

Ces erreurs ont ete rencontrees en production et sont documentees pour eviter repetition :

- `date:` sans guillemets au niveau racine (YAML parse comme time.Time)
- `taxonomy.technology` et `taxonomy.category` manquants
- `output.include:` au lieu de `output.fields:` (voir correction 24)
- `pkg/bin/lia_scan_engine` (chemin obsolete) -- utiliser `bin/lia_scan_engine`
- `pci_dss` avec cle `control` au lieu de `requirement`
- Remediation en tableau (format legacy) au lieu d'objet `{duration, steps}`
- Pattern arithmetique `N - N` dans computed fields (Phase07 false positive)
- Commentaires SAFE contenant "CVE-" dans test_data -- comptes comme VULNERABLE par le validateur ratio (voir correction 20)
- `block_short` invalide -- verifier la taxonomie (voir correction 21)
- `version_lt()` syntaxe FONCTION flaggee comme invalide par `validate_operators_functions.py` (voir correction 25)
- `status: informational` invalide -- valeurs acceptees: `deprecated|experimental|stable|test`
- Dict MITRE dans `references:` -- URLs uniquement dans cette section
- `collection_script` path inexistant sur disque -- verifier avec `ls scripts/collect/{tech}/`
- Version format 2 segments invalide -- toujours 3 segments minimum: `"3.8"` -> `"3.8.0"`
- Champ utilise dans `output.computed` non declare dans `output.fields` -- deux causes possibles (faux positif double-quotes ou champ reel manquant)
- Chaines double-quotes non fermees dans computed fields -- faux positifs "CHAMPS UTILISES NON DEFINIS"

---

## Commandes Debug

```bash
# Verbose mode (plus de details)
VERBOSE=1 ./recette_rule_cli/validate_rules_recipe.sh /path/to/rule/

# Logs detailles dans fichier
./validate_rules_ultimate.sh /path/to/rule/ > debug.log 2>&1

# Verifier syntaxe YAML
python3 -c "import yaml; print(yaml.safe_load(open('rule.yml')))" 2>&1

# Verifier syntaxe JSON
python3 -m json.tool test_data.json > /dev/null && echo "JSON OK"
python3 -m json.tool R-*.json > /dev/null && echo "ReportRule OK"

# Test moteur seul
ENGINE="/home/mo0ogly/Bureau/vscode_lia_audit/bin/lia_scan_engine"
$ENGINE -multi -rules . -events test_data.json -quadrigramme TEST -date $(date +%Y%m%d)

# Compter matches vs attendu
MATCHES=$($ENGINE -multi -rules . -events test_data.json -quadrigramme TEST -date $(date +%Y%m%d) 2>&1 | grep -c "MATCH")
EXPECTED=$(python3 -c "import json; d=json.load(open('test_data.json')); print(sum(1 for x in d if x.get('_expected_match', False)))")
echo "Matches: $MATCHES / Expected: $EXPECTED"
```

---

## CRITICAL - Regle non chargee par le moteur (silent type-trap)

**Symptome:** `0 log rules evaluated, 0 structured rules evaluated` + `Matches: 0`,
alors que le YAML passe les validators de champs. Cause quasi-systematique : un champ
de type bool/float ecrit comme string -> yaml.v2 echoue a parser -> le moteur droppe
TOUTE la regle en silence (incident 2026-05-29, `kev_ransomware: 'Unknown'`).

**Gate BLOQUANT a ajouter dans la boucle VALIDATE** (distinct du compte de matches) :

```bash
# La regle DOIT etre chargee : structured rules evaluated >= 1
EVAL=$($ENGINE -multi -rules . -events test_data.json -quadrigramme TEST -date $(date +%Y%m%d) 2>&1 \
  | grep -oE '[0-9]+ structured rules evaluated' | grep -oE '^[0-9]+')
if [ "${EVAL:-0}" -lt 1 ]; then
  echo "CRITICAL: rule NOT loaded by engine (0 structured rules) -> YAML parse/type error"
fi
```

**Lint de type cve_info** (bool/float jamais quotes) -- chercher la faute avant de relancer :

```bash
# bool fields must be true/false (unquoted), never a quoted string
grep -nE "^\s*(is_kev|kev_ransomware|exploit_available|patch_available):\s*['\"]" *.yml \
  && echo "CRITICAL: bool cve_info field written as string -> engine drops rule"
# float fields must be numeric, never quoted
grep -nE "^\s*(cvss_score|epss_score|epss_percentile):\s*['\"]" *.yml \
  && echo "CRITICAL: float cve_info field quoted -> engine drops rule"
```

**Correction:** convertir au bon type (`kev_ransomware: true`, `cvss_score: 9.8`).
Pour `kev_ransomware`, valeur tri-etat CISA : `Known` -> `true`, `Unknown`/absent -> OMETTRE.
Reference contrat de type complet : `create-lia-rule/references/yaml-format.md` section "cve_info Block".

---

## HIGH - test_data: chaque cas doit porter _expected_match

**Symptome:** des cas test sans `_expected_match` (certaines regles harvest 2026-05-29 :
CISCO/DRUPAL/LITELLM/WINDOWS) -> impossible d'asserter vuln/safe par cas, distribution
non verifiable.

```bash
python3 -c "
import json,sys
a=json.load(open('test_data.json'))
miss=[i for i,x in enumerate(a) if '_expected_match' not in x]
print('CASES',len(a),'missing _expected_match:',miss)
sys.exit(1 if miss else 0)
"
```

**Correction:** ajouter `_expected_match` (bool) + `_test_description` prefixe
(`VULNERABLE`/`SAFE`) a CHAQUE cas. Voir `create-lia-rule/references/test-data-guide.md`.

---

## CRITICAL - ReportRule naming convention (jamais `R-A-A-*`)

**Convention LIA (source utilisateur 2026-05-29) :** le 1er token = la FONCTION,
le token suivant = la CATEGORIE/axe, puis le nom.
- `A-` = **A**nalyse (la regle de detection YAML). Ex YAML id : `A-A-DC-Coerce`
  = Analyse + categorie `A` (Architecture) + `DC-Coerce`.
- `R-` = **R**emediation (le ReportRule JSON). Le filename ReportRule se derive de
  l'id YAML en REMPLACANT le `A-` (Analyse) de tete par `R-` (Remediation) :
  `A-{CAT}-{nom}`  ->  `R-{CAT}-{nom}`.

| Categorie | Lettre |
|-----------|--------|
| Architecture | A |
| Security | S |
| Compliance/Governance | C (CGOV) |
| Health | H (HEAL) |
| Traceability | T |
| Vulnerability | V (VULN) |
| Privileged (PingCastle) | P |

**Erreur a NE JAMAIS produire :** `R-A-A-<nom>.json` (double `A-`). Cela vient de
prefixer `R-` a l'id complet (`R-` + `A-A-DC-Coerce`) au lieu de remplacer le `A-`
de tete. Mauvais : `R-A-A-DC-Coerce.json`. Bon : `R-A-DC-Coerce.json`.

Symptomes voisins corriges la meme session : `R-NoGPOLLMNR.json` (categorie absente)
-> `R-A-...`/`R-S-...` ; `R-A-L-LimitBlankPasswordUse.json` (lettre parasite) ->
`R-A-LimitBlankPasswordUse.json`.

### Normalisation de l'id YAML `A-A-*` (2eme lettre = axe reel)

La 2eme lettre de l'id est l'AXE de la regle (= le dossier `ADDS/{AXIS}/`). Un id
`A-A-*` n'est CORRECT que pour l'axe Architecture. Pour tout autre axe, le `A-A-`
est un bug PingCastle-conversion a corriger vers la lettre de l'axe :

| Axe (dossier) | axis_short | Lettre id | id correct |
|---------------|-----------|-----------|-----------|
| Architecture | ARCH | A | `A-A-*` (garder) |
| Security | SECU | S | `A-S-*` |
| Compliance/Governance | CGOV | C | `A-C-*` |
| Health | HEAL | H | `A-H-*` |
| Traceability | TRAC | T | `A-T-*` |
| Vulnerability | VULN | V | `A-V-*` |
| Privileged (PingCastle) | P | P | `A-P-*` |

Renommage d'un id `A-A-X` (axe non-ARCH) -> `A-{AXE}-X` touche, de facon coherente :
1. YAML `id:` (ligne ~2)
2. YAML `classification.rule_id:`
3. nom du fichier YAML : `git mv A-A-X.yml A-{AXE}-X.yml`
4. ReportRule : `git mv R-A-X.json R-{AXE}-X.json` + champ `rule_id` interne
Re-valider : ReportRule batch = GLOBAL PASS, et Phase 14 (Taxonomy Directory
Coherence) du recipe = 0 critical (la lettre d'axe matche `axis_short` -> ameliore
la coherence). Le rename n'affecte PAS le nombre de cas test ni les champs (les
scores recipe/ultimate pre-existants restent inchanges -- ne pas les confondre avec
un echec du rename).

**Detection :**
```bash
find lia_rules/rule_analysis -name "R-A-A-*.json"   # doit etre vide
# ids A-A-* hors ARCH (a renommer) :
for ax in SECU CGOV HEAL TRAC VULN; do grep -rl '^id: A-A-' lia_rules/rule_analysis/ADDS/$ax --include="*.yml"; done
```

**Correction :**
- Si un sibling canonique `R-{CAT}-{nom}.json` enrichi existe deja dans le dossier :
  le `R-A-A-*` est un duplicata de l'ancien format (`description` string, 0 steps) ->
  `git rm` le `R-A-A-*` (l'historique git le conserve).
- Sinon : `git mv R-A-A-<nom>.json R-A-<nom>.json` (preserve le contenu).
Le champ `rule_id` interne reste = l'id YAML (`A-A-...`) ; seul le FILENAME est
normalise. Le matcher live (`check_reportrule_linkage.py`) resout par dossier (tier2).
Ne PAS toucher les 178 `id:` YAML `A-A-*` (convention source, escalade R3 si migration).
