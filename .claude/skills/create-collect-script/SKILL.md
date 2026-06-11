---
name: create-collect-script
description: "Create LIA-Scan collection scripts v5.1 -- agentic loop architecture. Loop autonome: OBJECTIVE -> RESEARCH -> ACT -> OBSERVE -> EVALUATE -> REPLAN? -> ALIGN (G6 YAML contract) -> COMPLETE. Enforces MOTOR_FIX_010 (raw data only, no detection logic). PowerShell/Bash for any technology on any platform. NEW v5.1: Phase ALIGN aligns required_files.pattern in existing YAML rules with actual script output filenames. Composes with /konrad-kurze (meta-cognitive auditor invoked before the 3rd REPLAN on the same gate)."
---

> **PREMIERE ACTION OBLIGATOIRE :** Annoncer "Using create-collect-script skill v5.1. Reading reference files..." comme premiere ligne de reponse.

# LIA-Scan Collection Script Creation Skill v5.1

**IMPORTANT:** Avant de commencer, lire les fichiers de reference :

1. `Read: _alire/01_DOCUMENTATION/rules/01_Guides/COLLECTION_SCRIPTS_QUICK_REFERENCE.md`
2. `Read: _alire/01_DOCUMENTATION/rules/01_Guides/4_SIGMA_AUTHORING_GUIDE.md` (Sections 4-5)

## Path conventions (W0.2 -- client level in /collect/)

Collected data is written under the `/collect/` base resolved through
`system_variables.COLLECT_PATH` (R5 PostgreSQL first). Two layouts are
supported in parallel; the resolver (`cmd/sigma_web/collect_path_resolver.go`)
tries the NEW layout first and transparently falls back to the LEGACY layout.
Existing directories are never moved.

1. NEW layout (preferred for any new campaign):

   ```
   <COLLECT_BASE>/<CLIENT_QUADRIGRAMME>/<TECHNO>/<YYYYMMDD>/
   ```

   * `CLIENT_QUADRIGRAMME` -- 2..16 chars, `^[A-Z0-9_]{2,16}$` (ex: `ACME`,
     `BANK01`, `CUSTOMER_X`). Validated in Go; anything containing `/`, `\`,
     `.` or lowercase is rejected with a `SECURITY` log event.
   * `TECHNO` -- short technology code, `^[A-Z0-9_]{1,32}$` (ex: `ADDS`,
     `DOCK`, `GO`, `POSTGRESQL`, `REACT`, `UB25`). This is the value that
     historically lived under `<QUAD>` in the legacy layout.
   * `YYYYMMDD` -- 8 digit campaign date.

2. LEGACY layout (still supported read/write):

   ```
   <COLLECT_BASE>/<TECHNO>/<YYYYMMDD>/
   ```

   Any generated script MUST be able to run against either layout. Never
   hardcode the client level; resolve it from caller parameters.

Resolution order (Go): `ResolveCampaignPath(client, techno, date)` tries
new layout first, then legacy. Creation: `EnsureCampaignDirectory(client,
techno, date)` creates the new layout when `client != ""`, otherwise the
legacy layout.

Generated collection scripts MUST accept the output directory as a parameter
(for example `-OutputDir <PATH>` in PowerShell, `--output <PATH>` in Bash).
The platform resolves the final path via `ResolveCampaignPath` and passes it
in; the script itself is client-agnostic and never composes the path.

## Arguments

- `$ARGUMENTS[0]` - Technologie: `ADDS`, `EXCHANGE`, `POSTGRESQL`, `DOCKER`, `UBUNTU`, `FORTINET`, `IVANTI`, etc.
- `$ARGUMENTS[1]` - Plateforme: `windows` (PowerShell), `linux` (Bash), `api` (REST API)
- `$ARGUMENTS[2]` - Description: ce que le script doit collecter

---

## Boucle Agentique v5.1

```
OBJECTIVE
  -> identifier technologie + methode de collecte disponible
RESEARCH (sonnet)
  -> niveau 1: scripts existants pour cette techno (Glob)
  -> niveau 2: scripts d'une techno similaire (Glob)
  -> niveau 3: WebSearch obligatoire (min 4 requetes)
  -> EXIT si 0 methode trouvee apres 3 niveaux: ESCALATE
ACT (haiku)
  -> ecrire script(s) PowerShell/Bash depuis templates
  -> creer test_collect.sh + sample_output.json + OBJECTCLASS_REFERENCE.md
OBSERVE (haiku)
  -> executer 5 gates de validation (placeholders, MOTOR_FIX_010, URLs, JSON, IPs fictives)
EVALUATE
  -> SUCCESS: toutes les 5 gates passent -> ALIGN
  -> FAILURE: au moins 1 gate echoue -> REPLAN
REPLAN (sur chaque FAILURE)
  -> identifier la gate en echec
  -> alternative 1: corriger le champ en violation (placeholder, logique detection)
  -> alternative 2: changer de methode de collecte (si gate 3: trouver plus de sources)
  -> alternative 3: simplifier le script (reduire ObjectClasses si gate 4 bloque)
  -> LOOP avec correction ciblee
  -> apres 3 FAILURE consecutifs sur la meme gate: ESCALATE
ALIGN (haiku) -- Gate G6 YAML Contract Alignment
  -> verifier que chaque regle YAML de la techno pointe vers un script existant (.sh ou .ps1)
  -> verifier que required_files.pattern correspond au glob de sortie canonique du script
  -> auto-corriger les patterns desalignes dans les fichiers YAML
  -> SUCCESS: 0 desalignement / 0 script manquant -> COMPLETE
  -> PARTIAL: corrections appliquees, aucun blocage residuel -> COMPLETE (rapport inclus)
  -> FAILURE: script manquant non resolvable ou > 50 regles impactees -> ESCALATE
COMPLETE
  -> RETEX AFFICHE obligatoirement
```

### Model Selection

| Phase | Model | Raison |
|-------|-------|--------|
| RESEARCH niveau 3 (WebSearch) | `sonnet` | Internet research + evaluation qualite sources |
| RESEARCH niveaux 1-2 + ACT + OBSERVE + REPLAN | `haiku` | Glob, lecture scripts, ecriture templates |

---

## Quality Hooks

| Hook | Gate | Commande |
|------|------|---------|
| QH-CS1 | Zero placeholder | `grep -rn '\{[A-Za-z_]+\}' scripts/collect/{tech}/*.ps1 scripts/collect/{tech}/*.sh 2>/dev/null` |
| QH-CS2 | MOTOR_FIX_010 | `grep -rn 'is_compliant\|is_vulnerable\|CVE.*_is_' scripts/collect/{tech}/*.ps1 scripts/collect/{tech}/*.sh 2>/dev/null` |
| QH-CS3 | Research proof | `grep -oE 'https?://[^ ]+' scripts/collect/{tech}/COLLECTION_RESEARCH.md \| wc -l` (min 3) |
| QH-CS4 | JSON valide | `jq 'length' scripts/collect/{tech}/sample_output.json 2>/dev/null` (min 2) |
| QH-CS5 | Pas d'IPs fictives | `grep -E '192\.0\.2\.|198\.51\.100\.|203\.0\.113\.' scripts/collect/{tech}/sample_output.json` |
| QH-CS6 | YAML contract alignment | Voir Phase ALIGN -- scripts existants + patterns aligns |

**G1-G5 : chaque gate qui echoue = FAILURE -> REPLAN immediatement.**
**G6 : execute apres G1-G5 SUCCESS -- corrections auto puis COMPLETE.**

---

## REGLES ABSOLUES

### ZERO PLACEHOLDER

```
INTERDIT dans tout .ps1 / .sh:
  {default_port}     {Technology}     {tech_lowercase}
  TODO:              FIXME:           PLACEHOLDER
  "example.com"      "server01"       "corp.local"
  "changeme"         "YOUR_VALUE"     {any_braces}
```

### MOTOR_FIX_010

```
COLLECTION = DONNEES BRUTES uniquement
  - Version, Hostname, Configuration, Statuts
  - Normalisation de format autorisee (9.1R14.4 -> 9.1.14.4)
  - Boolean depuis etat systeme (systemctl is-enabled -> true/false)

DETECTION = DANS LA REGLE YAML uniquement
  - Comparaison de versions
  - Verification de conformite
  - Calcul de vulnerabilite
```

**INTERDIT dans un script de collecte :**
```powershell
$CVE_2026_1234_is_vulnerable = ($major -lt 12) -or ($major -eq 12 -and $minor -lt 8)
$is_compliant = ($setting -eq "true")
$is_patched = ($kbs -contains "KB5000871")
$check_result = if ($version -lt "2.0") { "FAIL" } else { "PASS" }
```

---

## Phase RESEARCH (GATE BLOQUANTE)

**Cette phase est BLOQUANTE. Aucun script ne peut etre ecrit tant qu'elle n'est pas completee.**

#### Niveau 1 : Scripts existants pour cette technologie (IDEAL)

```bash
Glob: scripts/collect/{technology}/*.ps1
Glob: scripts/collect/{technology}/*.sh
Glob: scripts/collect/{technology_lowercase}/*.ps1
```

Si trouve : extraire ObjectClass, champs, methodes. FIN de la recherche.

#### Niveau 2 : Scripts d'une technologie similaire (ACCEPTABLE)

```bash
# Fortinet -> paloalto, cisco, checkpoint | Redis -> mongodb, postgresql
Glob: scripts/collect/{similar_technology}/*.ps1
```

Si trouve : adapter le pattern. FIN de la recherche.

#### Niveau 3 : WebSearch obligatoire (si niveaux 1 et 2 echouent)

```bash
WebSearch: "{technology} powershell management module cmdlets"
WebSearch: "{technology} REST API documentation endpoints"
WebSearch: "{technology} CLI command line version check"
WebSearch: "{technology} security audit configuration export"
```

**Minimum requis (4 sur 7) :**

| # | Information | Obligatoire |
|---|------------|-------------|
| 1 | Methode de collecte (cmdlet, API, CLI) | OUI |
| 2 | Commande exacte | OUI |
| 3 | Champs disponibles (Version, Hostname...) | OUI |
| 4 | Format de sortie (JSON, PSObject, text) | OUI |
| 5 | Authentification | si applicable |
| 6 | Pre-requis (module, package) | si applicable |
| 7 | URL documentation officielle | recommande |

Documenter dans `scripts/collect/{technology}/COLLECTION_RESEARCH.md` AVANT d'ecrire le script.
Template : voir `references/test_and_validation.md`

**EVALUATE RESEARCH :**
- SUCCESS (niveaux 1 ou 2) : methode identifiee -> ACT (AUTONOMOUS)
- SUCCESS (niveau 3) : min 4 informations sur 7 -> ACT (SUPERVISED : confirmer avec utilisateur)
- FAILURE : aucune methode apres 3 niveaux -> ESCALATE

---

## Phase ACT

**Structure des scripts :**

| Plateforme | Pattern | Exemple |
|-----------|---------|---------|
| PowerShell | `Collect-{Technology}.ps1` | `Collect-Fortinet.ps1` |
| PowerShell CVE | `Collect-{Technology}-Version.ps1` | `Collect-Ivanti-Version.ps1` |
| PowerShell CIS | `Collect-{Technology}-CIS.ps1` | `Collect-Ubuntu-CIS.ps1` |
| Bash | `Collect-{Technology}.sh` | `Collect-PostgreSQL.sh` |

**Decision multi-scripts** (depuis regles YAML existantes) :

```bash
Grep: "ObjectClass:" path=lia_rules/rule_analysis/{TECHNOLOGY}/ glob=*.yml output_mode=content
```

| ObjectClasses distincts | Strategie |
|------------------------|-----------|
| 1-3 | Quick Start (1 script) - AUTONOMOUS |
| 4-8 | Multi recommande (2-3 scripts) - SUPERVISED |
| 9-15 | Multi obligatoire (3-5 scripts) - SUPERVISED |
| 16+ | Architecture complexe - SUPERVISED |

Templates complets :
- PowerShell : `references/powershell_template.md`
- Bash : `references/bash_template.md`

Creer aussi : `test_collect.sh` + `sample_output.json` + `OBJECTCLASS_REFERENCE.md`
Templates : `references/test_and_validation.md`

**EVALUATE ACT :**
- Scripts ecrits sans placeholder visible -> OBSERVE
- Placeholder detecte en relecture -> REPLAN immediat (ne pas attendre la gate)

---

## Phase OBSERVE (5 Gates)

```bash
# Gate 1: Zero placeholder
grep -rn '\{[A-Za-z_]+\}' scripts/collect/{tech}/*.ps1 scripts/collect/{tech}/*.sh 2>/dev/null

# Gate 2: Zero MOTOR_FIX_010 violations
grep -rn 'is_compliant\|is_vulnerable\|CVE.*_is_' scripts/collect/{tech}/*.ps1 scripts/collect/{tech}/*.sh 2>/dev/null

# Gate 3: COLLECTION_RESEARCH.md avec URLs reelles (min 3)
grep -oE 'https?://[^ ]+' scripts/collect/{tech}/COLLECTION_RESEARCH.md 2>/dev/null | wc -l

# Gate 4: sample_output.json valide (min 2 objets)
jq 'length' scripts/collect/{tech}/sample_output.json 2>/dev/null

# Gate 5: Pas d'IPs fictives RFC 5737
grep -E '192\.0\.2\.|198\.51\.100\.|203\.0\.113\.' scripts/collect/{tech}/sample_output.json 2>/dev/null
```

---

## Phase EVALUATE

| Verdict | Condition | Decision |
|---------|-----------|----------|
| SUCCESS | Toutes les 5 gates passent | ALIGN |
| FAILURE | Au moins 1 gate echoue | REPLAN |

---

## Phase REPLAN (sur chaque FAILURE)

Identifier la gate en echec et choisir :

**Gate 1 echoue (placeholder) :** Corriger chaque `{valeur}` avec une valeur reelle issue de la phase RESEARCH. LOOP vers OBSERVE.

**Gate 2 echoue (MOTOR_FIX_010) :** Supprimer la logique de detection, deplacer dans la colonne "REGLE YAML". LOOP vers OBSERVE.

**Gate 3 echoue (< 3 URLs) :** Relancer WebSearch niveau 3 avec des requetes differentes. LOOP vers ACT.

**Gate 4 echoue (sample_output.json invalide) :** Corriger le JSON (quoting, encoding). Si impossible de produire 2 objets representatifs : simplifier les ObjectClasses. LOOP vers OBSERVE.

**Gate 5 echoue (IPs fictives) :** Remplacer par des adresses representant un environnement de test realiste. LOOP vers OBSERVE.

**Apres 2 FAILURE consecutifs sur la meme gate (gate Konrad-Kurze, AVANT la 3eme) :**

Avant d'escalader a l'utilisateur, invoquer `/konrad-kurze` via le Skill tool (model: **sonnet**) avec scope = `create-collect-script/{techno}/{gate_id}`. Passer en evidence : `decision_log.jsonl` de la session, le script en cours, et le contenu de la gate qui echoue.

Lire la directive emise dans `_alire/02_LOGS/Journals/meta/directives/KD-{id}.json` :
- Si `risk_level = LOW` ET `injection.operation = ADD` ET `requires_approval = false` : appliquer la directive comme correctif a la 3eme tentative (par exemple : ajout d'une probe RESEARCH supplementaire, ajout d'un check pre-OBSERVE). Logger `action="KONRAD_DIRECTIVE_APPLIED"` dans decision_log.jsonl.
- Sinon (MEDIUM / HIGH ou requires_approval) : surface la directive a l'utilisateur en MEME temps que l'ESCALATE. Ne pas auto-appliquer.

Cas specifiques particulierement utiles ici :
- META_DATA_AMNESIA : la regle YAML correspondante n'existe pas encore -> Konrad signale qu'il manque la cible (sortie OBSERVE n'a personne a alimenter).
- GHOST_REDUNDANCY : un script tres similaire existe deja pour la meme techno -> Konrad signale qu'il faut etendre l'existant plutot que dupliquer.
- LEMANRUSS_TAINT : la methode de collecte choisie est invalide depuis la phase RESEARCH (les WebSearch decoulent d'une fausse hypothese sur la techno).

**Apres 3 FAILURE consecutifs sur la meme gate :** ESCALATE (avec la directive Konrad incluse si emise).

---

## Phase ALIGN (Gate G6 -- YAML Contract Alignment)

Execute automatiquement apres SUCCESS sur G1-G5. Deux verifications independantes.

### G6a : collection_script pointe vers un fichier existant

```bash
TECH_DIR="lia_rules/rule_analysis/{TECH_UPPER}"

# Extract collection_script values from all rules and verify file exists
grep -rn 'collection_script:' "${TECH_DIR}" --include="*.yml" | while IFS= read -r match; do
  file=$(echo "${match}" | cut -d: -f1)
  script_path=$(echo "${match}" | sed 's/.*collection_script:[[:space:]]*"//;s/".*//')
  if [ -n "${script_path}" ] && [ ! -f "${script_path}" ]; then
    echo "MISSING: ${script_path}  (referenced in ${file})"
  fi
done
```

Si des scripts manquants sont detectes :
- 1-3 scripts manquants : mettre a jour le champ `collection_script` dans les YAMLs pour pointer vers le script cree
- Plus de 3 scripts distincts manquants : ESCALATE (techno sous-equipee, scope depasse)

### G6b : required_files.pattern correspond au glob canonique du script

Identifier le glob canonique depuis le script cree :
```bash
# Exemple pour docker -> "docker_config.json" (fichier fixe)
# Exemple pour go    -> "go_*.json" (timestamp dans le nom)
grep -E 'OUTPUT_FILE|OUTPUT=|output_file' scripts/collect/{tech}/*.sh scripts/collect/{tech}/*.ps1 2>/dev/null | head -5
```

Puis verifier l'alignement dans les regles YAML :
```bash
TECH_DIR="lia_rules/rule_analysis/{TECH_UPPER}"
CANONICAL_GLOB="{canonical_glob}"  # ex: "docker_config.json" ou "go_*.json"

# Collect all distinct patterns used in rules
grep -rn 'pattern:' "${TECH_DIR}" --include="*.yml" | grep -oP '"[^"]+"' | tr -d '"' | sort -u | while read -r pattern; do
  # Check if a file matching CANONICAL_GLOB would also match this pattern
  # Simple mismatch: pattern references a completely different filename root
  echo "PATTERN: ${pattern}  vs CANONICAL: ${CANONICAL_GLOB}"
done
```

Auto-correction si patterns desalignes (exemple : ancienne valeur -> nouvelle valeur) :
```bash
# Replace stale pattern in all rules for this tech
OLD_PATTERN="docker_containers.json"
NEW_PATTERN="docker_config.json"
grep -rl "\"${OLD_PATTERN}\"" "${TECH_DIR}" --include="*.yml" | xargs sed -i "s|\"${OLD_PATTERN}\"|\"${NEW_PATTERN}\"|g"
echo "Patched $(grep -rl "\"${NEW_PATTERN}\"" "${TECH_DIR}" --include="*.yml" | wc -l) rules"
```

### Verdict G6

| Verdict | Condition | Action |
|---------|-----------|--------|
| SUCCESS | 0 script manquant + 0 pattern desaligne | COMPLETE |
| PARTIAL | Corrections appliquees, aucun blocage residuel | COMPLETE (rapport inclus dans RETEX) |
| FAILURE | Script manquant non resolvable OU > 50 regles impactees | ESCALATE |

---

## RETEX (AFFICHE OBLIGATOIREMENT en fin de loop)

```
RETEX create-collect-script {TECH} {DATE}
Iterations : {N}
Verdict final : SUCCESS / FAILURE
Methode de collecte : {cmdlet|API|CLI}
ObjectClasses : {liste}
Scripts crees : {liste fichiers}
Gates : G1={PASS|FAIL} G2={PASS|FAIL} G3={PASS|FAIL} G4={PASS|FAIL} G5={PASS|FAIL} G6={PASS|FAIL|PARTIAL}
G6 Scripts existants : {N}/{N} | Patterns aligns : {N}/{N} | Corrections auto : {N}
Violations MOTOR_FIX_010 evitees : {liste alternatives rejetees}
```

---

## Decomposition des sous-taches

Au demarrage, decomposer la demande en sous-taches independantes :

- [ ] Sous-tache 1 : Phase RESEARCH (Glob scripts existants + WebSearch si niveau 3)
- [ ] Sous-tache 2 : ecriture script(s) PowerShell/Bash depuis templates (Phase ACT)
- [ ] Sous-tache 3 : creer `sample_output.json` + `test_collect.sh` + `COLLECTION_RESEARCH.md`
- [ ] Sous-tache 4 : Phase OBSERVE -- 5 gates G1-G5
- [ ] Sous-tache 5 : Phase ALIGN (G6) -- YAML contract alignment
- [ ] Sous-tache 6 : RETEX affiche + decision_log + commit

Utiliser `TaskCreate` pour tracker si > 3 sous-taches.

## Plan d'execution

Pour tout nouveau script de collecte :

1. Creer `_alire/tracking/PLAN_COLLECT_{TECH}_{YYYY-MM-DD}.md` au demarrage (avant tout ecriture).
2. Template : `_alire/tracking/PLAN_TEMPLATE.md`.
3. Cocher chaque sous-tache a la completion.
4. Si replanification : Status -> REPLANIFIE + lien vers nouveau plan.

Pour une modification ponctuelle sur un script existant (< 2 champs) : plan inline suffit.

## Outils declares

| Outil | Usage | Retry policy |
|-------|-------|--------------|
| `Read`, `Grep`, `Glob` | Explorer scripts existants (niveaux 1-2 RESEARCH) avant d'ecrire | N/A |
| `Write`, `Edit` | Creer/modifier .ps1, .sh, sample_output.json, YAML | N/A |
| `Bash grep gates G1-G5` | Validation OBSERVE (placeholder, MOTOR_FIX_010, URLs, JSON, IPs) | 1 retry apres fix |
| `Bash jq` | Valider sample_output.json (gate G4) | N/A |
| `Skill(konrad-kurze)` | Avant 3eme FAILURE consecutif sur une meme gate | Obligatoire |
| `WebSearch` | Niveau 3 RESEARCH si aucun script similaire trouve | min 4 requetes |
| `TaskCreate` | Tracking si > 3 sous-taches | N/A |

Selection dynamique : outil choisi selon le contexte, pas de liste figee.

## Tracabilite (OBLIGATOIRE)

Creer `_alire/tracking/PLAN_COLLECT_{TECH}_{YYYY-MM-DD}.md` au demarrage.

Logger dans `_alire/02_LOGS/Journals/decision_log.jsonl` :
```bash
echo '{"timestamp":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","session":"collect-{TECH}","action":"METHODE_CHOISIE","reasoning":"...","alternatives_rejected":["..."],"outcome":"PASS|FAIL","confidence":"high|medium|low","plan_ref":"PLAN_COLLECT_{TECH}_{DATE}.md"}' >> _alire/02_LOGS/Journals/decision_log.jsonl
```

RETEX en fin de session si score agentique < 40/50 -> `_alire/02_LOGS/Journals/retex/RETEX_COLLECT_{TECH}_{YYYY-MM-DD}.md`.

---

## Checklist finale

**Recherche (BLOQUANT) :**
- [ ] Phase RESEARCH completee : methode de collecte identifiee
- [ ] COLLECTION_RESEARCH.md cree avec queries + URLs + resultats (min 3 URLs)
- [ ] ObjectClass base sur une source verifiable

**MOTOR_FIX_010 (BLOQUANT) :**
- [ ] ZERO champ de detection (is_compliant, is_vulnerable, CVE_*_is_vulnerable)
- [ ] ZERO comparaison de version dans le script
- [ ] Seules transformations autorisees : normalisation format, boolean systeme

**Qualite script :**
- [ ] Header docstring complet
- [ ] Gestion erreurs (try/catch ou set -o pipefail)
- [ ] Output JSON valide + Encoding UTF8
- [ ] Commandes de collecte REELLES
- [ ] Authentification securisee (PSCredential, env vars)

**Tests et Sample :**
- [ ] test_collect.sh cree et executable
- [ ] sample_output.json avec 2-3 objets representatifs (versions reelles)
- [ ] Champs requis : ObjectClass, Hostname, Version, CollectionDate

**YAML Contract (G6) :**
- [ ] G6a : collection_script de chaque regle YAML pointe vers un fichier .sh ou .ps1 existant sur disque
- [ ] G6b : required_files.pattern correspond au glob canonique de sortie du script
- [ ] Corrections auto appliquees si desalignement detecte

---

## VERIFICATION GATE (BLOQUANT)

Apres execution, AVANT de declarer termine :

- [ ] Phase RESEARCH completee : `COLLECTION_RESEARCH.md` existe avec min 3 URLs reelles
- [ ] Gate G1 propre : zero `{placeholder}` dans les scripts
- [ ] Gate G2 propre : zero logique de detection MOTOR_FIX_010 (is_vulnerable, is_compliant...)
- [ ] Gate G4 propre : `sample_output.json` valide (jq length >= 2)
- [ ] Gate G5 propre : zero IP fictive RFC 5737 dans sample_output.json
- [ ] Gate G6 propre : collection_script YAML pointe vers fichier existant + pattern aligne
- [ ] `test_collect.sh` cree et executable
- [ ] RETEX affiche dans le chat (OBLIGATOIRE)
- [ ] `decision_log.jsonl` loge les choix de methode + alternatives rejetees

Si un gate echoue : STOP, REPLAN, re-gate. JAMAIS declarer "done" avec un gate rouge.

---

## Anti-patterns interdits

```powershell
# INTERDIT: Valeur inventee
$results += [PSCustomObject]@{ Version = "12.5.0.0"; Hostname = "server01" }

# INTERDIT: Logique de detection
$isVulnerable = ($version -lt "12.8.0")
$isCompliant = ($setting -eq "enabled")

# INTERDIT: Commande inventee
fake_tool --get-version

# INTERDIT: JSON fictif
echo '[{"ObjectClass":"fake","Version":"1.0"}]' > output.json
```

---

## Scoring agentique

| Critere | Score |
|---------|-------|
| C1 Decomposition : sous-taches identifiees (RESEARCH / ACT / OBSERVE / ALIGN) ? | /10 |
| C2 Planification : PLAN_COLLECT_*.md cree et suivi ? | /10 |
| C3 Replanification : /replan declenche sur echecs consecutifs (gate repetee 3x) ? | /10 |
| C4 Outillage : Glob + WebSearch + gates bash + /konrad-kurze invoques dynamiquement ? | /10 |
| C5 Tracabilite : decision_log + RETEX produits ? | /10 |

Score total /50 -- >= 40 : Exemplaire | 30-39 : Acceptable | < 30 : RETEX obligatoire

---

## References

- Templates PowerShell : `references/powershell_template.md`
- Templates Bash : `references/bash_template.md`
- Tests + validation + sample : `references/test_and_validation.md`
- Multi-scripts strategy : `references/multi_scripts_strategy.md`
- Scripts existants : `scripts/collect/`
- MOTOR_FIX_010 : `_alire/01_DOCUMENTATION/rules/01_Guides/4_SIGMA_AUTHORING_GUIDE.md` (Section 0)
- Quick Reference : `_alire/01_DOCUMENTATION/rules/01_Guides/COLLECTION_SCRIPTS_QUICK_REFERENCE.md`
- BANK scripts : `scripts/collect/BANK/BANK_COLLECTION_SCRIPTS_DOCUMENTATION.md`
- Status scripts manquants : `_alire/tracking/collect_scripts_status.json`

*Skill v5.1 - 2026-04-23 - ALIGN phase (G6): YAML contract alignment*
