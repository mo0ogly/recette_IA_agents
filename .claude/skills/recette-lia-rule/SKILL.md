---
name: recette-lia-rule
description: "LIA-Scan rule validation (recette) v5.0 -- Boucle agentique autonome. Cycle VALIDATE -> EVALUATE -> FIX -> re-VALIDATE -> LOOP until exit 0. 164 checks (recipe 41 + ultimate 91 + reportrule 11 + engine). Autonomous fix loop with regression gates. Composes with /konrad-kurze (meta-cognitive auditor invoked before the 3rd REPLAN on the same check)."
---

# LIA-Scan Rule Validation (Recette) v5.0 -- Boucle Agentique

L'agent valide et corrige une regle en boucle autonome jusqu'a exit 0 sur les 164 checks.

## Coeur : la boucle

```
VALIDATE (164 checks)
  -> EVALUATE
       exit 0 -> COMPLETE -> RETEX (AFFICHE)
       exit 1/2/3 -> FIX (par severite CRITICAL->HIGH->MEDIUM)
                       -> re-VALIDATE -> EVALUATE -> LOOP
                       3 echecs meme check -> REPLAN (2+ alternatives)
                       3 REPLAN meme check -> ESCALADE
```

**Pas de confirmation entre iterations.** L'agent boucle jusqu'a exit 0. Escalade sur : where clause, CRITICAL non resolvable, corrections en cascade qui aggravent le score.

## Arguments

`$ARGUMENTS` : chemin vers un repertoire de regle ou un glob pattern.
- Single : `lia_rules/rule_analysis/TECH/VULN/A-VULN-XXX/`
- Batch : `lia_rules/rule_analysis/TECH/VULN/A-VULN-*/`

---

## Phase 1 : VALIDATE (Observe)

### Execution des 4 validators

```bash
PROJECT_ROOT="/opt/lia-sec/dev"
cd "$PROJECT_ROOT/recette"

# 1. Moteur LIA-Scan
chmod +x "$RULE_DIR/test_rule.sh" && bash "$RULE_DIR/test_rule.sh"

# 1b. GATE engine-load (BLOQUANT, distinct du compte de matches) :
#     "0 structured rules evaluated" = regle droppee en silence par yaml.v2
#     (champ bool/float ecrit comme string, ex kev_ransomware: 'Unknown'). CRITICAL.
#     Lint type cve_info + correction : voir CORRECTIONS_REFERENCE.md section
#     "Regle non chargee par le moteur (silent type-trap)".

# 2. Recipe (41 checks)
./validate_rules_recipe.sh "$RULE_DIR/"

# 3. Ultimate (91 checks)
./validate_rules_ultimate.sh "$RULE_DIR/"

# 4. ReportRule (11 checks)
./validate_reportrules.sh "$RULE_DIR/R-*.json"
```

**Option tout-en-un :**
```bash
./validate_rules_ALL.sh "$RULE_DIR/" --run-test --show-progress
```

**Exit codes :** 0=PASS, 1=CRITICAL, 2=HIGH, 3=MEDIUM.

---

## Phase 2 : EVALUATE (Orient -- classification formelle)

| Exit | Verdict | Action |
|------|---------|--------|
| 0 | **SUCCESS** | -> COMPLETE |
| 3 | **PARTIAL** | Fix MEDIUM -> re-validate |
| 2 | **FAILURE** | Fix HIGH -> re-validate |
| 1 | **FAILURE** | Fix CRITICAL -> re-validate (ESCALADE si where clause) |

Compter `error_count` total avant chaque iteration. Stocker dans working memory.

---

## Phase 3 : FIX -> re-VALIDATE (Act -> Observe -> Evaluate)

### Ordre de correction (BLOQUANT -- par severite, JAMAIS par effort)

```
CRITICAL (exit 1) -> HIGH (exit 2) -> MEDIUM (exit 3)
```

### Procedure par correction

1. Identifier l'erreur dans le rapport
2. Consulter [CORRECTIONS_REFERENCE.md](CORRECTIONS_REFERENCE.md)
3. Appliquer la correction
4. **Re-valider les 3 validators** (QH-R1)
5. Comparer `error_count_after` vs `error_count_before` (QH-R2)
   - Si `error_count_after >= error_count_before` -> **ROLLBACK + REPLAN**
   - Si diminue -> correction validee, passer au suivant

### REPLAN (jamais la meme correction deux fois)

Declenche quand :
- error_count augmente apres correction
- 3 echecs sur le meme check
- Corrections en cascade

Procedure :
1. Diagnostiquer pourquoi la correction echoue
2. Generer 2+ alternatives
3. Logger dans `decision_log.jsonl`
4. 2 REPLAN meme check (gate Konrad-Kurze, AVANT le 3eme) :
   - Invoquer `/konrad-kurze` via le Skill tool (model: **sonnet**) avec scope = `recette-lia-rule/{rule_id}/{check_id}`. Passer en evidence : YAML, decision_log.jsonl, rapport recette en cours, et l'historique des fix appliques.
   - Lire la directive emise dans `_alire/02_LOGS/Journals/meta/directives/KD-{id}.json`.
   - Si `risk_level = LOW` ET `injection.operation = ADD` ET `requires_approval = false` : appliquer comme 3eme alternative (par exemple : ajouter un cas de test manquant, completer un tag MITRE, ajouter une reference). Logger `action="KONRAD_DIRECTIVE_APPLIED"`.
   - Sinon : surface la directive a l'utilisateur en MEME temps que l'ESCALADE.

   Cas particulierement utiles :
   - GHOST_REDUNDANCY : la correction reapplique systematiquement la meme transformation qui re-casse un autre check (cascade infinie).
   - META_DATA_AMNESIA : check ultimate echoue parce qu'un fichier annexe (ReportRule, test_data) est absent ou non aligne avec la regle.
   - LEMANRUSS_TAINT : les corrections supposent un fix qui contredit le rapport recette reel (ex: "j'ai corrige X" mais le check echoue toujours sur Y).

5. 3 REPLAN meme check -> ESCALADE utilisateur (avec la directive Konrad incluse si emise).

---

## Phase 4 : COMPLETE (Apprentissage)

### Resume final (OBLIGATOIRE -- afficher)

```
RESUME VALIDATION: {RULE_ID}
  Score global: XX/100 ({RATING})
  Exit code: 0 (PASS)

  Recipe (41 checks):     XX/100 - Exit 0
  Ultimate (91 checks):   XX/100 - Exit 0
  ReportRule (11 checks): XX/100 - Exit 0

  Corrections appliquees: N
  Iterations boucle: N
  Verdict: PRODUCTION READY
```

**Seuils :** >= 95 Excellent | 85-94 Bon | 70-84 Review | < 70 Refonte

### RETEX (OBLIGATOIRE -- AFFICHER)

```
RETEX - {RULE_ID} ({DATE})
Score agentique : {N}/50

| Critere | Score |
|---------|-------|
| C1 Decomposition | /10 |
| C2 Planification | /10 |
| C3 Replanification | /10 |
| C4 Outillage | /10 |
| C5 Tracabilite | /10 |

Iterations boucle : {N}
Corrections : {N} appliquees, {N} rollback
REPLAN : {N} declenches

Q1. Checks echoues que le skill aurait pu prevenir ?
Q2. Checks qui necessitent un nouveau validator ?
Q3. Erreurs a capitaliser dans CORRECTIONS_REFERENCE.md ?
Q4. Actions immediates (effort S) -> les executer
```

### Intelligence diagnostique (batch mode)

Si >3 regles echouent sur le meme check :
1. Identifier le pattern commun
2. Proposer un fix batch (QH-R3 gate -- confirmation avant batch >3 regles)
3. Verifier si le validateur est incomplet

---

## Model Selection

Tous les roles sont **haiku** -- validation = execution de scripts + parsing.

| Phase | Modele |
|-------|--------|
| Validate (run scripts) | **haiku** |
| Analyze results | **haiku** |
| Fix errors | **haiku** |
| RETEX | **haiku** |

---

## Perimetre d'autonomie

| Action | Autonome |
|--------|----------|
| Executer validators | OUI |
| Fix HIGH/MEDIUM | OUI (max 3 iterations par check) |
| Fix CRITICAL | ESCALADE |
| Modifier where clause | ESCALADE |
| Batch fix >3 regles | ESCALADE (confirmation) |
| Rollback correction | OUI |

---

## Memoire 3 niveaux

### Niveau 1 : Travail (session)

- `error_count` avant/apres chaque correction
- Liste des corrections appliquees
- Compteur iterations boucle + REPLAN

### Niveau 2 : Longue (inter-sessions)

- [CORRECTIONS_REFERENCE.md](CORRECTIONS_REFERENCE.md) (28+ corrections connues)
- `decision_log.jsonl` (patterns recurrents)
- RETEX precedents sur la meme technologie

### Niveau 3 : Action Journal

```json
{"timestamp":"ISO","action":"VALIDATE|FIX|REVALIDATE|ROLLBACK|REPLAN","target":"file","error_count_before":5,"error_count_after":3}
```

---

## Regles de comportement

1. **TOUJOURS valider AVANT de corriger** -- ne pas deviner
2. **CORRIGER par severite** (CRITICAL->HIGH->MEDIUM), JAMAIS par effort
3. **Re-valider apres chaque correction** (QH-R1)
4. **Rollback si error_count augmente** (QH-R2)
5. **NE PAS modifier la where clause** sans escalade
6. **JAMAIS la meme correction deux fois** -- si echec, REPLAN avec alternatives
7. **RETEX affiche** meme si tout est vert

---

## References

| Fichier | Contenu |
|---------|---------|
| [CORRECTIONS_REFERENCE.md](CORRECTIONS_REFERENCE.md) | 28+ corrections connues par check |
