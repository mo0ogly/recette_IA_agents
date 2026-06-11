---
name: recette-live-rule
description: "Recette live v5.0 -- Boucle autonome VALIDATE->EVALUATE->FIX->re-VALIDATE sur donnees VM reelles (Windows/Linux). SUCCESS/PARTIAL/FAILURE apres chaque action, REPLAN sur chaque FAILURE avec 2+ alternatives, RETEX affiche obligatoire. Platform detect, 7 checks structurels, cross-validation YAML/collector/test_data, moteur Go reel."
---

> **PREMIERE ACTION OBLIGATOIRE :** Annoncer "Using recette-live-rule skill. Analysing target..." comme premiere ligne de reponse.

# LIA-Scan Recette Live v5.0 -- Boucle Autonome

Boucle autonome de validation regles LIA-Scan sur donnees VM reelles.
Windows (PowerShell Direct) ou Linux (SSH/SCP).

**Infrastructure reference (paths, VM, collectors, formats):** `references/infrastructure.md`

---

## Model Selection (MANDATORY)

| Phase | Model | Rationale |
|-------|-------|-----------|
| VALIDATE (platform detect, data freshness, engine test) | `haiku` | Script execution, trivial |
| EVALUATE (cross-validation YAML/collector/test_data, diagnosis) | `sonnet` | Raisonnement cross-fichiers |
| FIX (corrections mecaniques) | `haiku` | Corrections scripted |
| RETEX | `haiku` | Report generation |

EVALUATE est le seul role qui justifie sonnet.

## Boucle autonome (MANDATORY)

```
PLATFORM_DETECT -> STRUCTURAL_VALIDATE -> DATA_VALIDATE -> CROSS_VALIDATE
     -> ENGINE_TEST -> EVALUATE -> FIX? -> re-VALIDATE -> LOOP or COMPLETE
                           ^___________________|
                           LOOP si FAILURE, REPLAN si 2+ FAILURE
```

Modes :
- **Single** : 1 regle -> boucle directe
- **Batch** : N regles -> boucle par regle, rapport agrege final
- **Batch > 10 regles** : delegation sub-agents (haiku, GATE QH-L1 enforced)

---

## Platform Detection (MANDATORY au demarrage)

```bash
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]] || command -v cmd.exe &>/dev/null; then
    PLATFORM="windows"
else
    PLATFORM="linux"
fi
```

| Aspect | Windows | Linux (VPS) |
|--------|---------|-------------|
| Engine | `lia-test.exe` / `lia-scan.exe` | `lia-test` / `lia_scan_engine` |
| Test script | `test_rule.ps1` (PowerShell) | `test_rule.sh` (Bash) |
| Collection VM | PowerShell Direct | SSH / SCP |
| BOM handling | Auto (test_rule.ps1) | `tail -c +4` si BOM |
| Recette scripts | N/A | `validate_rules_ALL.sh` (164 checks) |

> Full paths per platform : `references/infrastructure.md`

---

## Step 0 : Identify Target

`$ARGUMENTS` peut etre :
- Chemin regle : `IIS10/SECU/A-S-IIS-HstsHeaderIsSet` (single)
- Repertoire categorie : `IIS10/SECU` (batch)
- Domaine : `IIS10` (batch)
- `all` ou `*` (batch global)

---

## VALIDATE -- Phase 1 : Checks structurels (7 checks)

| # | Check | Criticite |
|---|-------|-----------|
| 1 | Fichiers presents (.yml, test_data.json, test_rule.sh/ps1, R-*.json) | CRITICAL |
| 2 | `data_source.collection_script` pointe vers fichier existant | HIGH |
| 3 | `data_source.required_files[].pattern` matche output collector reel | HIGH |
| 4 | `test_data.json` contient `_expected_match` sur chaque objet | CRITICAL |
| 5 | `test_data.json` utilise `ObjectClass` correct | CRITICAL |
| 6 | `test_data.json` contient les champs de `object_detection.where` | HIGH |
| 7 | Ratio `_expected_match: true` >= 55% | MEDIUM |

Commande : `validate_rules.ps1` (Windows) ou `validate_rules_ALL.sh` (Linux).

Evaluation :
```
## Observation -- Structural
Result: {7/7 OK | N/7 OK, failing checks listed}
Status: SUCCESS (7/7) | PARTIAL (>= 5/7, CRITICAL pass) | FAILURE (CRITICAL fail)
```

---

## VALIDATE -- Phase 2 : Freshness donnees VM

```powershell
# Windows
$dataAge = (Get-Date) - (Get-Item $REAL_DATA_PATH).LastWriteTime
if ($dataAge.TotalDays -gt 7) { Write-Host "[WARN] Data is $($dataAge.Days) days old" }
```

```bash
# Linux
data_age=$(( ($(date +%s) - $(stat -c %Y "$REAL_DATA_PATH")) / 86400 ))
if [ "$data_age" -gt 7 ]; then echo "[WARN] Data is ${data_age} days old"; fi
```

Si re-collecte necessaire (SUPERVISED) :
1. Deploy collectors via `deploy_lia_collectors.ps1`
2. Retrieve JSON -> `collects/*/real_data/`
3. Regenerer test_data.json via `generate_test_data.ps1`

---

## VALIDATE -- Phase 3 : Cross-validation YAML/collector/test_data

Coherence tripartite :
```
YAML (where clause) <-> Collector (output fields) <-> test_data.json (objects)
     ObjectClass           ObjectClass in JSON          ObjectClass in objects
     Detected fields       Collected fields             Present fields
     Operators             Value types                  Coherent values
```

- Chaque champ du YAML `where` doit exister dans l'output collector
- Chaque champ du YAML `where` doit exister dans les objets test_data
- Valeurs vulnerables dans test_data = ce que le collector produirait sur systeme non durci
- Valeurs safe = systeme durci

---

## VALIDATE -- Phase 4 : Test moteur Go

**TOUJOURS le vrai moteur Go. JAMAIS un pseudo-moteur.**

**QH-L1 (BLOCKING avant test)**: verifier `_expected_match` sur chaque objet test_data.

#### Test sur test_data.json (synthetique)

Windows :
```powershell
powershell.exe -ExecutionPolicy Bypass -File "$RULE_DIR/test_rule.ps1"
# Avec donnees lab reelles :
powershell.exe -ExecutionPolicy Bypass -File "$RULE_DIR/test_rule.ps1" -RealData
```

Linux :
```bash
"$RULE_DIR/test_rule.sh"
# Ou directement :
"$ENGINE" --rule "$RULE_DIR/$RULE_ID.yml" --events "$RULE_DIR/test_data.json" --format txt
```

Exit codes : 0=PASS (matches trouves) | 1=NO_MATCH | 2=ERROR

BOM handling (Linux) :
```bash
if [ "$(head -c 3 "$TD" | xxd -p)" = "efbbbf" ]; then
    tail -c +4 "$TD" > "$TD.tmp" && mv "$TD.tmp" "$TD"
fi
```

#### Test sur donnees VM reelles

Lire `data_source` du YAML -> identifier collector et pattern -> trouver fichier par **ObjectClass** (pas par nom de fichier) -> test.

Interpretation :
- `PASS` + matches > 0 = anomalies detectees sur lab (attendu si lab non durci)
- `NO_MATCH` = aucune anomalie (verifier si lab est durci pour ce check)
- `ERROR` = probleme format/parsing (BOM, cles dupliquees, UTF-16)

---

## EVALUATE -- Verdict par regle

```
## Observation -- Engine Test
Result: {N matches, score test_data X/Y}
Expected: {matches sur cas vulnerables, 0 match sur cas safe}
Status: SUCCESS | PARTIAL (FP/FN < 10%) | FAILURE (FP/FN >= 10% ou ERROR)
```

---

## FIX -- Correction (si EVALUATE = FAILURE)

**Ordre de correction STRICT par severite -- JAMAIS par effort :**
`CRITICAL -> HIGH -> MEDIUM`

**QH-L2 (BLOCKING apres chaque fix)** : re-valider la regle complete. Si score diminue -> ROLLBACK.

Tableau de decision :

| Probleme | Action |
|----------|--------|
| Champ manquant dans collector | Fix source .ps1 (QH-L4) -> re-deploy -> re-collect -> regenerer -> revalider |
| ObjectClass mismatch | Fix YAML (pas collector) -> regenerer test_data -> revalider |
| collection_script incorrect | Fix chemin dans YAML -> revalider |
| test_data sans `_expected_match` | Regenerer via generate_test_data -> revalider |
| Ratio `_expected_match` trop bas | Ajuster generate_test_data (plus de variantes) -> regenerer -> revalider |
| FP/FN moteur | Verifier conditions YAML where + valeurs test_data -> fix source -> revalider |

**QH-L3** : si > 3 regles echouent sur meme check -> fix batch AVANT de continuer N corrections individuelles.

**QH-L4** : modifier TOUJOURS le source .ps1 reel, jamais un wrapper ou une copie.

**MOTOR_FIX_010** : les collectors collectent, les regles detectent. JAMAIS de logique de detection dans les collectors.

Apres FIX -> retour VALIDATE (re-validation complete de la regle).

---

## REPLAN -- Sur chaque FAILURE

```
## Replan -- {RULE_ID} Step {N}
Failure cause: {diagnostic}
Root cause: MISSING_FIELD | OBJECTCLASS_MISMATCH | COLLECTOR_BUG | YAML_LOGIC | ENV_ISSUE
Alternatives:
  A. {approche A} -- rejetee car {raison}
  B. {approche B} -- selectionnee car {raison}
  C. {approche C} -- fallback si B echoue
New plan: {etapes mises a jour}
```

Regles REPLAN :
- JAMAIS modifier la clause `where` sans confirmation utilisateur (SUPERVISED)
- JAMAIS retenter sans changer au moins 1 variable
- Pattern identique sur 3+ regles -> fix batch (QH-L3) avant suite
- 3 REPLAN consecutifs -> escalade utilisateur

---

## COMPLETE -- Rapport final (RETEX AFFICHE obligatoire)

```
============================================
  RECETTE LIVE - {TARGET}
  Date: {DATE}
============================================

PLAN: {PLAN_FILE}
MODE: {single|batch} ({N} regles)

--- RESULTS ---

| Rule | Structure | Collector | TestData | Engine | Verdict |
|------|-----------|-----------|----------|--------|---------|
| A-S-IIS-... | 7/7 OK | OK | OK | 14/14 | SUCCESS |
| A-VULN-... | 6/7 | KO:path | OK | 12/14 | FIX |

--- CORRECTIONS APPLIED ---
1. [A-S-IIS-...] Fixed collection_script path
2. [Collect-IIS.ps1] Added field XYZ

--- METRICS ---
Rules validated: XX/XX
Global score: XX%
REPLAN applied: N
Total time: XX min

--- VERDICT ---
[ ] PRODUCTION READY (100% SUCCESS)
[ ] REVIEW NEEDED (>85% SUCCESS, minor corrections)
[ ] FIX REQUIRED (<85%, corrections needed)
[ ] BLOCKED (external dependency: VM, collector, etc.)
```

---

## Memoire 3 niveaux

**Working memory** (mise a jour apres chaque regle) :
```
Completed: [rule_ids]
Current: {rule_id} -- EVALUATE en cours
Pending: [rule_ids restants]
REPLAN count: N
Fixes applied: [{rule_id, fix_type, severity}]
Global score: XX%
```

**Long-term memory** : `RECETTE_LOG.jsonl` par session.

**Action journal** : chaque action loggee dans `RECETTE_LOG.jsonl` :
```json
{"timestamp":"ISO8601","action":"VERB","target":"rule_or_scope","details":"...","status":"SUCCESS|PARTIAL|FAILURE","role":"EVALUATE|FIX|VALIDATE"}
```

---

## Tracabilite

- Plan : `_alire/tracking/PLAN_RECETTE_LIVE_{TARGET}_{YYYY-MM-DD}.md`
- Decision log : `_alire/02_LOGS/Journals/decision_log.jsonl`
- Action journal : `RECETTE_LOG.jsonl` (dans le repertoire de la regle ou du batch)

---

## Anti-patterns (rationalisations invalides)

| Rationalisation | Pourquoi invalide |
|-----------------|------------------|
| "J'utilise une valeur par defaut pour test_data" | MOTOR_FIX_010 + regle no-placeholder |
| "Je saute la collecte VM, le cache suffit" | Si > 7 jours, donnees potentiellement obsoletes |
| "Je fixe le MEDIUM d'abord, c'est rapide" | Ordre par SEVERITE, jamais par effort |
| "Le test moteur est impossible sur Windows" | lia-test.exe + test_rule.ps1 sont disponibles |
| "Je commite alors que 3 regles sont KO" | Commiter uniquement quand score stable/ameliore |
| "Je fixe regle par regle" | Si pattern commun detecte (QH-L3), batch fix d'abord |
| "Je modifie un wrapper plutot que le source .ps1" | QH-L4 : toujours editer le vrai collector source |

---

## Invocation

```bash
/recette-live-rule IIS10/SECU/A-S-IIS-HstsHeaderIsSet   # Single
/recette-live-rule IIS10/SECU                            # Batch categorie
/recette-live-rule EXCHANGE                              # Batch domaine
/recette-live-rule all                                   # Global
/recette-live-rule IIS10 --refresh                       # Avec re-collecte forcee
```

---

## Scoring agentique (toujours affiche)

| Critere | Description | Score |
|---------|-------------|-------|
| Decomposition | Objectif decompose en sub-tasks avant action | /10 |
| Planification | Plan cree et suivi | /10 |
| Replanification | Chaque FAILURE -> REPLAN avec 2+ alternatives | /10 |
| Outillage dynamique | Bons outils choisis par contexte | /10 |
| Tracabilite | Journal + plan + rapport complet | /10 |

**Total /50**

| Score | Rating |
|-------|--------|
| 45-50 | Excellent |
| 35-44 | Bon |
| 25-34 | Moyen |
| <25 | Faible |
