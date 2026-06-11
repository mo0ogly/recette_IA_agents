---
name: scorecard-builder
description: Consolide les rapports d'audit en scorecard JSON avec scoring pondere, detection de regressions, et quality gates. Integre regression-detector. Se declenche sur "/scorecard-builder", "calcule le score", "scorecard", "consolide les rapports", ou quand audit-pdca appelle C.3.
---

# SCORECARD-BUILDER -- Consolidation, scoring et regressions

Parse les rapports d'audit (brainstorm, securite, tests), applique le scoring
pondere, detecte les regressions vs cycle precedent, et applique les quality gates.

## TRACABILITE AGENTIQUE (OBLIGATOIRE)

### Plan persistant
Creer `_alire/tracking/PLAN_SCORECARD_{CYCLE}_{YYYY-MM-DD}.md` (template: `_alire/tracking/PLAN_TEMPLATE.md`).

### Decision log
Logger dans `_alire/02_LOGS/Journals/decision_log.jsonl` les decisions non-triviales.
Format: `{"timestamp","session","action","reasoning","alternatives_rejected":[],"outcome","confidence","plan_ref"}`

### Replanification
Si 2 etapes echouent consecutivement → INVOQUER `/replan`.

### Scoring agentique (/50)
En fin de workflow, scorer sur : Decomposition, Planification, Replanification, Outillage dynamique, Tracabilite.

---

## Syntaxe

```
/scorecard-builder --brainstorm=<dir> --security=<file> --tests=<file> --config=<scoring_config> [--prev=<prev_scorecard>] [--output=<file>] [--gate]
```

| Argument | Description | Defaut |
|----------|-------------|--------|
| `--brainstorm` | Repertoire D_BRAINSTORM/ (rapports agents) | obligatoire |
| `--security` | Fichier C_SECURITY.md | optionnel |
| `--tests` | Fichier C_TESTS.md | optionnel |
| `--config` | SCORING_CONFIG.json (poids, checks, gates) | obligatoire |
| `--prev` | C_SCORECARD.json du cycle precedent | optionnel (cycle 1 = sans) |
| `--output` | Fichier de sortie | `C_SCORECARD.json` |
| `--gate` | Activer les quality gates (bloque si min_score non atteint) | false |

---

## WORKFLOW

### Etape 1 : Extraction des scores par domaine

```
Pour chaque fichier dans --brainstorm/*.md :
  EXTRAIRE domaine = nom du fichier (sans .md)
  EXTRAIRE score_agent = regex "## Score : (\d+)/100"
  EXTRAIRE forces = section "## Forces" ou "## DEJA FAIT"
  EXTRAIRE gaps = section "## Faiblesses" ou "## GAPS"
  EXTRAIRE quick_wins = section "## Quick Wins"
  COMPTER findings = nombre de lignes dans gaps

  SI fichier vide ou score non trouve :
    score_agent = 0
    WARN "Rapport {domaine} invalide ou vide"
```

### Etape 2 : Application des penalites securite/tests

```
SI --security fourni :
  COMPTER findings_critical = lignes avec "CRITICAL" ou "CRITIQUE"
  COMPTER findings_high = lignes avec "HIGH" ou "HAUTE"
  penalite_secu = (findings_critical * 5 + findings_high * 2) / 100
  penalite_secu = MIN(penalite_secu, 0.30)  # Cap a 30%

SI --tests fourni :
  EXTRAIRE go_compiles = "go build" resultat (0 ou 1)
  EXTRAIRE react_compiles = "npm run build" resultat (0 ou 1)
  EXTRAIRE coverage_go = pourcentage (0-100)
  EXTRAIRE coverage_react = pourcentage (0-100)
  penalite_tests = 0
  SI go_compiles == 0 : penalite_tests += 0.20
  SI react_compiles == 0 : penalite_tests += 0.20
  SI coverage_go < 30 : penalite_tests += 0.05
  SI coverage_react < 30 : penalite_tests += 0.05
```

### Etape 3 : Scoring pondere

```
CHARGER SCORING_CONFIG.json

Pour chaque domaine :
  weight = config.domains[domaine].weight
  score_brut = score_agent
  score_ajuste = score_brut * (1 - penalite_secu - penalite_tests)
  score_pondere = score_ajuste * weight / 100

  stocker {
    domaine, score_brut, score_ajuste, score_pondere, weight,
    findings_count, forces, gaps, quick_wins
  }

score_global = SUM(score_pondere pour tous les domaines)
score_global = ROUND(score_global, 0)
```

### Etape 4 : Detection regressions (si --prev)

```
SI --prev fourni :
  CHARGER prev_scorecard.json

  Pour chaque domaine :
    delta = score_ajuste_current - score_ajuste_previous
    SI delta < -5 :
      AJOUTER a regressions[] :
        domaine, score_prev, score_current, delta,
        "REGRESSION DETECTEE : -{abs(delta)} points"

  delta_global = score_global_current - score_global_previous
  tendance = "improving" si delta_global > 3
           | "stable" si -3 <= delta_global <= 3
           | "declining" si delta_global < -3
```

### Etape 5 : Quality gates (si --gate)

```
SI --gate :
  Pour chaque domaine dans config.domains :
    SI config.domains[domaine].gate existe :
      min_score = config.domains[domaine].gate.min_score
      SI score_ajuste < min_score :
        AJOUTER a blocked[] :
          domaine, score_ajuste, min_score,
          config.domains[domaine].gate.action  # BLOCK_FIX | WARN

  SI blocked non vide ET action == "BLOCK_FIX" :
    ALERTER : "QUALITY GATE ECHOUE -- Domaines bloques :"
    LISTER les domaines bloques avec score vs seuil
    RECOMMANDER : "Corriger ces domaines avant de continuer"
```

### Etape 6 : Generation outputs

**C_SCORECARD.json :**

```json
{
  "cycle": 2,
  "date": "2026-03-15T14:30:00Z",
  "perimetre": "grc",
  "score_global": 67,
  "score_global_previous": 45,
  "delta_global": 22,
  "tendance": "improving",
  "penalites": {
    "securite": 0.08,
    "tests": 0.05
  },
  "domaines": {
    "security": {
      "score_brut": 55,
      "score_ajuste": 48,
      "score_pondere": 9.6,
      "weight": 20,
      "score_previous": 30,
      "delta": 18,
      "findings": 12,
      "regression": false,
      "gate": {"min": 40, "status": "PASS"}
    }
  },
  "regressions": [],
  "blocked_gates": [],
  "top_improvements": [
    "fetchWithConfig: 5% -> 40% adoption (+25pts security)",
    "Audit trail created (0 -> 60pts architecture)"
  ],
  "top_gaps": [
    "EBIOS RM entities missing (benchmark_parity -30pts)",
    "i18n: 0 languages (completeness -15pts)"
  ],
  "quick_wins": [
    "Branch score_method on scoring algo (30min, +10pts)",
    "Add assigned_to on requirements (1h, +5pts)"
  ]
}
```

**Section DASHBOARD.md** (a inserer dans le dashboard multi-cycles) :

```markdown
| {cycle} | {date} | {score_global}/100 | +{delta} | {objectif} | {tendance} |
```

**Section Mermaid** (radar chart par domaine) :

```mermaid
%%{init: {'theme': 'dark'}}%%
pie title Score par domaine (Cycle {N})
    "Security" : {score_security}
    "Testing" : {score_testing}
    "Architecture" : {score_architecture}
    "Completeness" : {score_completeness}
    "Documentation" : {score_documentation}
    "Benchmark" : {score_benchmark}
```

---

## EXEMPLES

```bash
# Scorecard cycle 1 (pas de precedent)
/scorecard-builder \
  --brainstorm=_alire/pdca/grc/cycle_001/D_BRAINSTORM/ \
  --security=_alire/pdca/grc/cycle_001/C_SECURITY.md \
  --tests=_alire/pdca/grc/cycle_001/C_TESTS.md \
  --config=_alire/pdca/grc/SCORING_CONFIG.json \
  --output=_alire/pdca/grc/cycle_001/C_SCORECARD.json

# Scorecard cycle 2 (avec detection regressions + quality gates)
/scorecard-builder \
  --brainstorm=_alire/pdca/grc/cycle_002/D_BRAINSTORM/ \
  --security=_alire/pdca/grc/cycle_002/C_SECURITY.md \
  --tests=_alire/pdca/grc/cycle_002/C_TESTS.md \
  --config=_alire/pdca/grc/SCORING_CONFIG.json \
  --prev=_alire/pdca/grc/cycle_001/C_SCORECARD.json \
  --output=_alire/pdca/grc/cycle_002/C_SCORECARD.json \
  --gate

# Score rapide (brainstorm seul, pas de secu/tests)
/scorecard-builder \
  --brainstorm=_alire/temp/brainstorm/engine/ \
  --config=_alire/pdca/engine/SCORING_CONFIG.json
```

---

## REGLES

1. **Rapport sans `## Score` = score 0.** Le format est contractuel.
2. **Penalites plafonnees a 30%.** Evite qu'un seul probleme secu ecrase tout.
3. **Regression = delta > 5 points.** En dessous = bruit statistique.
4. **Quality gate BLOCK_FIX = stop.** Pas de passage au domaine suivant.
5. **Quality gate WARN = alerte.** Continue mais signale.
6. **Pas de score invente.** Si un rapport manque, le domaine est a 0 (pas ignore).

---

## ENCHAINEMENT AUTOMATIQUE (OBLIGATOIRE)

A la fin du scoring, TOUJOURS annoncer la prochaine etape :

```
ANNONCER : "Scorecard genere : {score}/100 (objectif {cible}). Prochaine etape : Phase A (Act) - remediation."
SI appele depuis audit-pdca : le flux continue automatiquement vers A.1 (Plan Mode)
SI appele en standalone : ANNONCER la remediation recommandee (domaines les plus bas)

JAMAIS terminer sans indiquer ce qui doit se passer ensuite.
```
