---
name: brainstorm-agents
description: Orchestre N agents paralleles sur un sujet avec collecte structuree des rapports. Reutilisable pour audit, recherche, comparaison multi-domaine, ou exploration codebase. Se declenche sur "/brainstorm-agents", "lance N agents", "brainstorming parallele", "audit multi-domaine", ou quand audit-pdca appelle D.2.
---

# BRAINSTORM-AGENTS -- Orchestrateur d'agents paralleles

Lance N agents en parallele, chacun specialise sur un domaine ou une question,
collecte les rapports structures, et consolide les resultats.

## Syntaxe

```
/brainstorm-agents <sujet> --domains="dom1,dom2,..." [--prompts=<file>] [--context=<file>] [--output=<dir>] [--timeout=600] [--mode=simple|crewai]
```

| Argument | Description | Defaut |
|----------|-------------|--------|
| `<sujet>` | Theme du brainstorming | obligatoire |
| `--domains` | Domaines (1 agent par domaine) | obligatoire |
| `--prompts` | Fichier contenant les prompts par domaine (section `## {domaine}`) | auto-genere |
| `--context` | Fichier(s) de contexte a injecter dans chaque agent | aucun |
| `--output` | Repertoire de sortie des rapports | `_alire/temp/brainstorm/` |
| `--timeout` | Timeout par agent en secondes | 600 |
| `--mode` | `simple` = 1 agent/domaine, `crewai` = 3 agents/domaine (analyst+specialist+architect) | simple |
| `--agent-type` | Type de subagent | `general-purpose` |

---

## TRACABILITE AGENTIQUE (OBLIGATOIRE)

### Plan persistant
Creer `_alire/tracking/PLAN_BRAINSTORM_{SUJET}_{YYYY-MM-DD}.md` (template: `_alire/tracking/PLAN_TEMPLATE.md`).

### Decision log
Logger dans `_alire/02_LOGS/Journals/decision_log.jsonl` les decisions non-triviales.
Format: `{"timestamp","session","action","reasoning","alternatives_rejected":[],"outcome","confidence","plan_ref"}`

### Replanification
Si 2 etapes echouent consecutivement → INVOQUER `/replan`.

### Scoring agentique (/50)
En fin de workflow, scorer sur : Decomposition, Planification, Replanification, Outillage dynamique, Tracabilite.

---

## MODEL SELECTION STRATEGY (COST OPTIMIZATION)

JAMAIS lancer un agent domaine sur opus. Specifier `model` explicitement sur chaque Agent tool call.

| Type de domaine | Model | Exemples |
|----------------|-------|----------|
| Compliance, grep patterns, file presence, documentation audit, dead code | `haiku` | R8/R10/R6 checks, doc coverage, naming conventions |
| Security OWASP, architecture review, UX, benchmark, code analysis | `sonnet` | security, architecture, testing, benchmark_parity |
| Orchestration (contexte principal) | herite parent | JAMAIS deleguer opus a un agent |

**Regle de selection automatique :**
```
SI domaine contient "compliance|documentation|naming|formatting|dead_code|coverage|presence" :
  model: "haiku"
SI domaine contient "security|owasp|architecture|testing|benchmark|ux|performance|code_quality" :
  model: "sonnet"
SINON :
  model: "sonnet"  # defaut safe (bon compromis cout/qualite)
```

**Cout relatif :** haiku ~x1, sonnet ~x5, opus ~x25. Un audit 6 domaines full opus = ~x150. Avec selection: ~x18 (economie x8).

---

## WORKFLOW

### Etape 1 : Preparation des prompts

```
SI --prompts fourni :
  LIRE le fichier, extraire section ## {domaine} pour chaque domaine
SINON :
  Pour chaque domaine dans --domains :
    GENERER un prompt par defaut :
      "Tu es un auditeur specialise sur le domaine '{domaine}'.
       Sujet : {sujet}
       Contexte : {context_resume}

       Ta mission :
       1. ANALYSER l'etat actuel du domaine dans le perimetre donne
       2. IDENTIFIER les forces et faiblesses (avec preuves : fichiers, lignes, comptages)
       3. SCORER le domaine de 0 a 100
       4. LISTER les gaps (ce qui manque) et les quick wins (facile a corriger)

       Format de reponse OBLIGATOIRE :
       ## Score : XX/100
       ## Forces (DEJA FAIT)
       ## Faiblesses (GAPS)
       ## Quick Wins
       ## Fichiers audites

       NE PAS CODER. Recherche et audit uniquement."
FIN SI
```

**Integration prompt-builder :** Si le fichier --prompts contient des prompts pre-generes par `/prompt-builder`, les utiliser directement. Sinon, generer des prompts generiques (moins precis mais fonctionnel).

### Etape 2 : Lancement parallele

```
DETERMINER N = nombre de domaines

SI mode == "simple" :
  LANCER N agents en PARALLELE (un seul message, N tool calls Agent) :
    Pour i = 1..N :
      Agent {agent-type} :
        name: "brainstorm-{domaine_i}"
        model: "{haiku|sonnet selon MODEL SELECTION STRATEGY}"
        prompt: prompt du domaine i + contexte
        run_in_background: true

SI mode == "crewai" :
  Pour chaque domaine :
    LANCER 3 agents SEQUENTIELS :
      1. analyst-{domaine} : "Inventorie l'etat actuel (fichiers, comptages, patterns)"
      2. specialist-{domaine} : "Compare avec les standards/benchmark, identifie gaps" (recoit output analyst)
      3. architect-{domaine} : "Propose remediation, estime effort, priorise" (recoit output specialist)
    -> Consolider les 3 outputs en 1 rapport pour le domaine
FIN SI
```

**Regles de lancement :**
- TOUJOURS lancer dans un seul message (pas de sequentiel entre domaines)
- Chaque agent est INDEPENDANT (pas de dependance entre domaines)
- `run_in_background: true` pour tous
- Si un agent echoue ou timeout, les autres continuent

### Etape 3 : Collecte et consolidation

```
ATTENDRE tous les agents (notification automatique a chaque completion)

Pour chaque agent termine :
  SAUVEGARDER le rapport dans {output}/{domaine}.md
  EXTRAIRE le score (regex "## Score : (\d+)/100")
  SI echec ou timeout :
    CREER {output}/{domaine}.md avec :
      "## Score : 0/100
       ## Erreur : Agent timeout/echec apres {timeout}s"

GENERER {output}/CONSOLIDATED.md :
  ## Synthese brainstorming : {sujet}
  Date : {date}
  Domaines : N
  Agents : N (dont X reussis, Y echecs)

  | Domaine | Score | Forces | Gaps | Quick Wins |
  |---------|-------|--------|------|------------|
  (1 ligne par domaine, extrait des rapports)

  ## Score global : MOYENNE(scores) /100
```

Output :
- `{output}/{domaine}.md` pour chaque domaine
- `{output}/CONSOLIDATED.md` (synthese)

---

## EXEMPLES

```bash
# Brainstorming audit GRC 6 domaines
/brainstorm-agents "Audit GRC LIA-SEC vs CISO Assistant" \
  --domains="security,testing,architecture,completeness,documentation,benchmark_parity" \
  --context=D_INVENTORY.json \
  --output=_alire/pdca/grc/cycle_001/D_BRAINSTORM/

# Brainstorming libre 3 questions
/brainstorm-agents "Comment ameliorer le moteur de regles LIA-Scan" \
  --domains="performance,extensibilite,maintenabilite" \
  --output=_alire/temp/brainstorm/engine/

# Mode CrewAI (3 agents/domaine) pour audit approfondi
/brainstorm-agents "Audit securite backend Go" \
  --domains="sql_injection,command_injection,auth,secrets" \
  --mode=crewai \
  --output=_alire/temp/brainstorm/security/

# Avec prompts pre-generes par prompt-builder
/brainstorm-agents "Benchmark ETL pipeline" \
  --domains="ingestion,transformation,loading,monitoring" \
  --prompts=_alire/pdca/etl/cycle_001/P_PLAN.md \
  --output=_alire/pdca/etl/cycle_001/D_BRAINSTORM/

# Recherche web multi-angles
/brainstorm-agents "Alternatives open-source a SonarQube" \
  --domains="go_linters,react_linters,sast,dast,license_check" \
  --agent-type=websearch-agent
```

---

## INTEGRATION AUDIT-PDCA

Cette skill est appelee automatiquement par `/audit-pdca` en phase D.2 :

```
audit-pdca D.2 :
  /brainstorm-agents "{perimetre} audit cycle {N}" \
    --domains={domaines_SCORING_CONFIG} \
    --prompts={P_PLAN.md} \
    --context={D_INVENTORY.json},{D_BENCHMARK.json} \
    --output={cycle_N}/D_BRAINSTORM/
```

---

## REGLES

1. **1 message = N agents.** Jamais de lancement sequentiel entre domaines.
2. **Agents read-only.** Ils ne codent pas, ils auditent/recherchent.
3. **Echec partiel OK.** Si 1 agent sur 6 echoue, les 5 rapports sont exploitables.
4. **Format obligatoire.** Chaque rapport DOIT contenir `## Score : XX/100` pour etre parseable.
5. **Timeout respecte.** Agent non termine apres timeout = rapport d'echec auto-genere.
6. **Mode crewai = 3x plus de tokens.** Utiliser seulement si mode simple insuffisant (cycle 2+).

---

## ENCHAINEMENT AUTOMATIQUE (OBLIGATOIRE)

A la fin du brainstorming, TOUJOURS annoncer la prochaine etape :

```
ANNONCER : "Brainstorm termine : {N}/{total} agents OK, rapports dans {output_dir}. Prochaine etape : /scorecard-builder (Phase C)."
SI appele depuis audit-pdca : le flux continue automatiquement vers C.3 (scorecard)
SI appele en standalone : ANNONCER les domaines avec findings critiques

JAMAIS terminer sans indiquer ce qui doit se passer ensuite.
```
