---
name: create-lia-rule
description: "LIA-Scan rule creation v5.0 -- Boucle agentique autonome niveau 5. Cycle OBJECTIVE -> RESEARCH -> GATE -> WRITE -> VALIDATE -> REPLAN -> LOOP or COMPLETE. PostgreSQL FIRST, MOTOR_FIX_010, 164 checks recette. Memoire 3 niveaux. Composes with /konrad-kurze (meta-cognitive auditor invoked before the 3rd REPLAN on the same validation check). Use when asked to create a new security rule, CVE rule, compliance rule."
---

# LIA-Scan Rule Creation v5.0 -- Boucle Agentique

L'agent cree une regle de bout en bout en boucle autonome : recherche, gate, ecriture, validation, correction, re-validation -- jusqu'a exit 0 sur les 164 checks.

## Coeur : la boucle

```
OBJECTIVE (CVE/compliance/bank)
  -> RESEARCH (PostgreSQL FIRST -> taxonomie -> scripts -> internet)
  -> GATE MOTOR_FIX_010 (3 niveaux champs)
  -> WRITE (YAML + test_data + test_rule + ReportRule + RESEARCH_EVIDENCE)
  -> VALIDATE (164 checks via /recette-lia-rule)
  -> EVALUATE
       SUCCESS (exit 0) -> COMPLETE -> RETEX (AFFICHE)
       FAILURE (exit 1/2/3) -> FIX -> re-VALIDATE -> LOOP
       3 echecs sur meme check -> REPLAN (2+ alternatives) ou ESCALADE
```

**Pas de confirmation entre phases.** L'agent boucle jusqu'a exit 0. Escalade uniquement sur : where clause modifiee, taxonomie manquante, CRITICAL non resolvable.

## Arguments

- `$ARGUMENTS[0]` -- Type : `cve`, `compliance`, `bank`, `hunting`
- `$ARGUMENTS[1]` -- Technologie : `ADDS`, `EXCHANGE`, `POSTGRESQL`, etc.
- `$ARGUMENTS[2]` -- Description ou CVE-ID

---

## Phase 1 : RESEARCH (Observe + Orient)

### PostgreSQL FIRST (BLOQUANT -- avant tout internet)

```sql
SELECT c.cve_id, c.cvss_score, c.cvss_severity, c.description,
       kev.cve_id IS NOT NULL as is_cisa_kev,
       ei.exploit_maturity, ei.total_exploit_count
FROM cve_nvd_data c
LEFT JOIN cisa_kev kev ON c.cve_id = kev.cve_id
LEFT JOIN exploit_intelligence_summary ei ON c.cve_id = ei.cve_id
WHERE c.cve_id = 'CVE-YYYY-XXXXX';
```

**Enrichissement cve_info complet (ne pas livrer maigre) + contrat de TYPE :** peupler le
bloc `cve_info` avec TOUT ce qui existe en base (cvss_vector, cwe, epss, kev dates,
kev_ransomware). ATTENTION TYPE : `is_kev`/`kev_ransomware`/`exploit_available`/
`patch_available` sont des **bool** (jamais `'Unknown'` ni string -> sinon le moteur droppe
la regle en silence) ; `cvss_score`/`epss_score`/`epss_percentile` sont des **float**.
Cross-check obligatoire rule vs `cve_nvd_data` (cwe/cvss_version/cvss_score) -- mismatch =
recherche advisory, jamais committer 2 verites. Requete + table de types complets :
[references/yaml-format.md](references/yaml-format.md) section "cve_info Block".

### Taxonomie + Scripts

```bash
# Taxonomie
python3 -c "import json; d=json.load(open('config/taxonomy/{TECH}_taxonomy.json')); ..."

# Scripts de collecte (arbre de decision)
ls scripts/collect/{TECH}*.ps1 scripts/collect/{TECH}*.sh 2>/dev/null  # Niveau 1
ls scripts/collect/ | grep -i {KEYWORD}                                 # Niveau 2
# Si absent -> /create-collect-script {TECH} (ESCALADE)
```

### GATE MOTOR_FIX_010 (3 niveaux -- BLOQUANT)

> **Lire :** `Read: .claude/skills/create-lia-rule/references/motor-fix-010.md`

| Niveau | Source | Action |
|--------|--------|--------|
| 1 | Script de collecte existant | Lire les champs du script |
| 2 | Regle existante meme techno | Copier le pattern ObjectClass/champs |
| 3 | Internet (vendor docs, CVE advisories) | WebSearch + validation |

**ZERO ObjectClass invente sans source verifiable.**
**ZERO pattern interdit** : pas de `is_compliant`, `is_vulnerable`, `is_affected`, `is_patched`, `check_result`.

Output : working memory avec ObjectClass, champs sources, CVE data.

---

## Phase 2 : WRITE (Decide + Act)

Creer tous les fichiers en une passe :

### Structure

```
rule_analysis/{TECH}/{AXIS}/{BLOCK}/A-{AXIS}-{TECH}-{Component}/
  A-{AXIS}-{TECH}-{Component}.yml
  R-A-{AXIS}-{TECH}-{Component}.json
  test_data.json
  test_rule.sh
  RESEARCH_EVIDENCE.md
```

**CVE = axe VULN obligatoirement.** Nom DOIT contenir `CVE-YYYY-XXXXX`.

### YAML (Sigma Extended -- section match)

> **Lire :** `Read: .claude/skills/create-lia-rule/references/yaml-format.md`

MOTOR_FIX_003 (5 computed fields avec `if()`), section `match:`, `ObjectClass: eq:` dans match ET where.

### test_data.json

**14+ cas realistes : 8-9 VULNERABLES (55-65%) + 5-6 SECURISES (35-45%).**
Descriptions SAFE sans "CVE"/"CRITICAL".

> **Lire :** `Read: .claude/skills/create-lia-rule/references/test-data-guide.md`

### ReportRule JSON (R-*.json)

risk_score echelle **0-100** (CRITICAL 90-100, HIGH 70-89, MEDIUM 40-69, LOW 1-39).
Remediation structuree : investigation + emergency_response + prevention.

> **Lire :** `Read: .claude/skills/create-lia-rule/TEMPLATE_REPORTRULE.md`

### test_rule.sh + RESEARCH_EVIDENCE.md

> **Lire :** `Read: .claude/skills/create-lia-rule/references/post-creation-gates.md`

---

## Phase 3 : VALIDATE -> EVALUATE -> FIX (La boucle)

### VALIDATE

Invoquer le skill `/recette-lia-rule` :

```
Skill: recette-lia-rule {RULE_PATH}/
```

**Exit codes :** 0=PASS, 1=CRITICAL, 2=HIGH, 3=MEDIUM.

### EVALUATE (classification formelle)

| Exit | Verdict | Action |
|------|---------|--------|
| 0 | **SUCCESS** | -> COMPLETE |
| 3 | **PARTIAL** | Fix MEDIUM -> re-validate |
| 2 | **FAILURE** | Fix HIGH -> re-validate |
| 1 | **FAILURE** | Fix CRITICAL -> re-validate (ESCALADE si where clause) |

### FIX (jamais la meme correction deux fois)

1. Identifier l'erreur exacte dans le rapport
2. Consulter `CORRECTIONS_REFERENCE.md` pour la correction connue
3. Appliquer la correction
4. **QH-C3** : re-valider. Si `error_count_after >= error_count_before` -> rollback + REPLAN

### REPLAN (sur 3 echecs meme check)

1. Diagnostiquer pourquoi la correction echoue
2. Generer 2+ alternatives (changer ObjectClass, changer niveau gate, simplifier la regle)
3. Logger dans `decision_log.jsonl` avec justification
4. 2 REPLAN meme check (gate Konrad-Kurze, AVANT le 3eme) :
   - Invoquer `/konrad-kurze` via le Skill tool (model: **sonnet**) avec scope = `create-lia-rule/{rule_id}/{check_id}`. Passer en evidence : YAML en cours, decision_log.jsonl, sortie du check qui echoue, et le test_data.json.
   - Lire la directive emise dans `_alire/02_LOGS/Journals/meta/directives/KD-{id}.json`.
   - Si `risk_level = LOW` ET `injection.operation = ADD` ET `requires_approval = false` : appliquer comme 3eme alternative (par exemple : ajouter une condition where, ajuster un modifier, completer test_data avec un cas manquant). Logger `action="KONRAD_DIRECTIVE_APPLIED"`.
   - Sinon : surface la directive a l'utilisateur en MEME temps que l'ESCALADE.

   Cas particulierement utiles ici :
   - CONVENTION_CONFLICT : where clause utilise un modifier banni ou viole MOTOR_FIX_010 (logique non auditable).
   - META_DATA_AMNESIA : test_data.json n'a pas de cas vulnerables OU pas de cas safe -> regle non testable.
   - GHOST_REDUNDANCY : la meme regle (ou une variante) existe deja dans `lia_rules/rule_analysis/`.
   - LEMANRUSS_TAINT : la classification CVE issue de PostgreSQL contredit la severite reelle (CVSS / CISA KEV) -> hypothese de scope erronee depuis Phase 1.

5. 3 REPLAN meme check -> ESCALADE utilisateur (avec la directive Konrad incluse si emise).

---

## Phase 4 : COMPLETE (Apprentissage)

### Post-creation gates

> **Lire :** `Read: .claude/skills/create-lia-rule/references/post-creation-gates.md`

5 gates : coherence, import, cross-reference, zero-placeholder, self-scoring.

### PostgreSQL tracking (CVE only)

Upsert dans `lia_cve_rules_coverage`.

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

Q1. Checks echoues que le skill aurait pu prevenir ?
Q2. Checks qui necessitent un nouveau validator ?
Q3. Erreurs a capitaliser dans CORRECTIONS_REFERENCE.md ?
Q4. Actions immediates (effort S) -> les executer avant de conclure
```

### Librarian Gate

```
[ ] PLAN_RULE_{ID}_{DATE}.md a jour (Status: TERMINE)
[ ] RETEX affiche dans la conversation
[ ] decision_log.jsonl a jour
[ ] Commit conventionnel + push
```

---

## Rationalisations invalides

| Rationalisation | Pourquoi invalide |
|-----------------|-------------------|
| "Je cherche sur internet d'abord" | PostgreSQL FIRST est BLOQUANT |
| "Je cree un ObjectClass logique" | Invente = REJETE par validator |
| "J'utilise is_vulnerable" | MOTOR_FIX_010 violation BLOQUANTE |
| "10 cas de test suffisent" | Minimum 14, ratio 55-65% vuln |
| "Je committe si exit 2" | COMMIT seulement si exit 0 |
| "Je skip la recette, le moteur passe" | Moteur = detection, recette = 164 checks |

---

## Model Selection

| Phase | Modele |
|-------|--------|
| Research CVE (Phase 1 PostgreSQL + web) | **sonnet** |
| Gate MOTOR_FIX_010 | **haiku** |
| Write files (Phase 2) | **haiku** |
| Validate + fix (Phase 3) | **haiku** |
| RETEX (Phase 4) | **haiku** |

---

## Perimetre d'autonomie

| Action | Autonome |
|--------|----------|
| PostgreSQL query + taxonomie | OUI |
| Gate Niveau 1-2 | OUI |
| Gate Niveau 3 (internet) | OUI si CVE-ID fourni |
| Creer taxonomie manquante | ESCALADE |
| Ecrire YAML + test_data + ReportRule | OUI apres gate validee |
| Fix recette HIGH/MEDIUM | OUI (max 3 iterations) |
| Fix recette CRITICAL | ESCALADE |
| Modifier where clause | ESCALADE |
| Invoquer /create-collect-script | ESCALADE |

---

## References

| Fichier | Contenu |
|---------|---------|
| [references/motor-fix-010.md](references/motor-fix-010.md) | Gate 3 niveaux + LISTE NOIRE |
| [references/yaml-format.md](references/yaml-format.md) | MOTOR_FIX_003 + champs + operateurs |
| [references/test-data-guide.md](references/test-data-guide.md) | Anti-mock + ratio + SAFE descriptions |
| [references/post-creation-gates.md](references/post-creation-gates.md) | Gates + tracking + RESEARCH_EVIDENCE |
| [references/retex-guide.md](references/retex-guide.md) | RETEX + erreurs frequentes |
| [TEMPLATE_REPORTRULE.md](TEMPLATE_REPORTRULE.md) | Templates ReportRule detailles |
| [CORRECTIONS_REFERENCE.md](CORRECTIONS_REFERENCE.md) | 28+ corrections connues |
