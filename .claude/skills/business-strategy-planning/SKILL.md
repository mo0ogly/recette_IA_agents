---
name: business-strategy-planning
description: Agentic business strategy and planning for LIASCAN/LIA-SEC. Produces investor-grade strategic artifacts -- Business Model Canvas, USP/value proposition, buyer personas, TAM/SAM/SOM market sizing, Go-To-Market plan, phased product roadmap, and 3-year financial forecast -- backed by REAL sourced data with zero confabulation (every claim cited file:line, FR vs international competitors separated, SHIPPED vs ROADMAP split). Use when the user asks to build or refine a business plan, business model, market sizing, GTM strategy, value proposition, competitive positioning, financial projection, fundraising strategy, or says "strategie business", "business model", "etude de marche", "TAM SAM SOM", "go-to-market", "plan financier", "positionnement concurrentiel". Composes with /investor-pitch (deck build), /pptx + /docx (export), /brainstorm-agents (parallel competitor research), /pptx-recette (deck QA). NOT for deck assembly only (use /investor-pitch) nor internal status (use internal-comms).
---

# Business Strategy & Planning (Agentic)

Build investor-grade strategy artifacts on a data-driven framework (market
research, value-prop design, BMC, market sizing, GTM, financial forecast), run
as an autonomous agentic loop with persistent planning, replanning, and full
traceability. Anti-confabulation is the core constraint: every figure and claim
is sourced or explicitly tagged `UNVERIFIED`.

## When to use

- Build or refine a business plan / business model for LIASCAN or a sub-product.
- Quantify a market (TAM/SAM/SOM) for a pitch or a raise.
- Design a value proposition / USP, buyer personas, or a Go-To-Market plan.
- Produce a 3-year financial forecast with defensible unit economics.
- Establish competitive positioning (FR vs international, separated).

For assembling the final slide deck, hand the artifacts to `/investor-pitch`
(orchestrated deck) or `/pptx` (direct build). This skill produces the STRATEGY;
those skills produce the DECK.

## Artifacts and references (progressive disclosure)

Load only the reference(s) the current deliverable needs.

| Artifact | Reference to load | Output |
|----------|-------------------|--------|
| Market sizing TAM/SAM/SOM | `references/market-sizing.md` | sourced 3-layer table |
| Business Model Canvas + USP | `references/business-model-canvas.md` | 9-block BMC + USP sentence |
| Personas + GTM + roadmap | `references/personas-gtm.md` | personas + GTM plan + 5-phase roadmap |
| 3-year financial forecast | `references/financial-model.md` | driver-based P&L + unit economics |

## Decomposition des sous-taches (C1)

Au demarrage, identifier les sous-taches independantes AVANT toute action :

- A : cadrer le livrable exact (quel artefact, audience FR/intl, langue, format)
  + critere de "done" -- Read le brief, Grep le corpus existant.
- B : collecter les faits sources -- corpus business-plan deja construit
  (`_alire/01_DOCUMENTATION/business-plan/`), code (`file:line`), sources
  externes citees -- Glob, Grep, Read, WebSearch/WebFetch si autorise.
- C : produire chaque artefact via la reference correspondante -- Write.
- D : gate anti-confabulation -- chaque claim cite une source reelle, Grep des
  tags `UNVERIFIED`, cross-check file:line.
- E : packaging / handoff -- pptx via /investor-pitch ou /pptx ; docx via /docx.

Dependances : C depend de B ; D depend de C ; E depend de D.
Artefacts independants (sizing vs BMC vs forecast) parallelisables via
`/brainstorm-agents` (1 agent sonnet par artefact ou par groupe de concurrents),
chaque agent recevant le contexte verifie pour ne PAS re-decouvrir en aveugle.

## Plan d'execution (C2)

Avant toute action, creer le plan persistant (sous-dir dedie, R7) :

```bash
mkdir -p _alire/tracking/business-strategy
cat > _alire/tracking/business-strategy/PLAN_BUSINESS_STRATEGY_$(date +%Y-%m-%d).md << 'EOF'
# Plan : Business strategy <livrable>
Date : <YYYY-MM-DD>
Status : EN_COURS

## Objectif
<1-2 phrases : quel artefact, quelle audience, FR/intl, langue>

## Etapes
- [ ] A : cadrer le livrable + critere done
- [ ] B : collecter faits sources (corpus + file:line + sources externes)
- [ ] C : produire artefact(s) via reference(s)
- [ ] D : gate anti-confabulation (zero claim non source)
- [ ] E : packaging / handoff

## Working Memory
Completed: [] | Current: A | Pending: [B,C,D,E]
Key findings:
Blockers:

## Decisions prises
## Ecarts et replanification
## Resultat
EOF
```

Cocher chaque etape `[x]` a la completion. Mettre a jour Working Memory a chaque
transition de phase. A la cloture : Status -> TERMINE + Resultat. Template :
`_alire/tracking/PLAN_TEMPLATE.md`.

## Adaptation et replanification (C3)

- 1 etape echoue (source introuvable, build pptx KO) : 1 retry avec parametre
  ajuste (autre source, autre requete), puis log si non-bloquant.
- 2 etapes consecutives echouent : STOP -> invoquer `/replan` -> produire
  `PLAN_*_REPLAN_*.md` avec lien vers le plan original. JAMAIS improviser.
- Source manquante pour une affirmation : ne PAS l'inventer (INTERDIT), la tagger
  `UNVERIFIED -- placeholder` et la lister dans les ecarts du plan.
- 3 echecs de replanification sur la meme etape : escalader a l'utilisateur avec
  le diagnostic complet.

Format REPLAN (dans PLAN_*_REPLAN_*.md) : Failure cause / Alternatives
considerees (A rejetee car..., B selectionnee car...) / New plan. Ne jamais
retenter exactement la meme action echouee. Logger action="REPLAN_TRIGGERED".

## Outils declares (C4)

Outils disponibles :
- Read : lire un fichier de corpus / code a chemin connu.
- Glob : localiser les artefacts du corpus business-plan (chemin multiple).
- Grep : chercher un fait, un `file:line`, ou les tags `UNVERIFIED`.
- Write : creer un nouvel artefact strategique (.md).
- Edit : raffiner un artefact existant (preferer sur Write).
- Bash : packaging (soffice/pdftoppm QA visuelle pptx), git.
- WebSearch / WebFetch : sourcer une donnee marche externe (si autorise) --
  TOUJOURS citer source + annee.
- Agent (sonnet) via `/brainstorm-agents` : recherche concurrentielle parallele.

Criteres de selection dynamique :
- Fait deja dans le corpus -> Grep/Read le corpus (PAS de re-recherche web).
- Chemin d'artefact inconnu -> Glob d'abord.
- Modification partielle d'un artefact -> Edit (pas Write).
- Donnee marche absente du corpus -> WebSearch + citation, sinon tag `UNVERIFIED`.
- Recherche multi-concurrents independante -> Agent sonnet parallele.

Retry policy : outil echoue -> 1 retry parametres ajustes -> 2e echec -> log
decision_log.jsonl + stop + signaler. JAMAIS ignorer un echec.

## Tracabilite agentique (C5)

### Decision log
Logger dans `_alire/02_LOGS/Journals/decision_log.jsonl` toute decision
non-triviale (segment beachhead, modele de revenu retenu, verdict
DIRECT/ADJACENT/NO-DIRECT-COMPETITOR sur un concurrent, rejet d'une source) :

```bash
echo '{"timestamp":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","session":"business-strategy","action":"ACTION","reasoning":"...","alternatives_rejected":["..."],"outcome":"...","confidence":"high|medium|low","plan_ref":"PLAN_BUSINESS_STRATEGY_*.md"}' >> _alire/02_LOGS/Journals/decision_log.jsonl
```

Ne PAS tracer : formatage, renommage, build mecanique.

### RETEX
En fin de session, si score agentique < 40/50 : identifier les criteres en
echec, documenter les actions correctives, sauvegarder dans
`_alire/02_LOGS/Journals/retex/RETEX_BUSINESS_STRATEGY_<YYYY-MM-DD>.md`.

## Workflow (framework data-driven)

Five-step research process before any artifact (detail in `references/market-sizing.md`):

1. Clarify the decision the artifact must support.
2. Desk research -- sourced figures (corpus first, then external + citation).
3. Primary signal -- interviews, pipeline, design-partner ACVs if available.
4. Reconcile -- top-down vs bottom-up same order of magnitude.
5. Insight + recommendation -- the number, the 2-3 assumptions, the sensitivity.

Then produce artifacts value-first: Segments -> Value Prop/USP -> Personas ->
GTM -> Market sizing -> Financial model. Load the matching reference per artifact.

## LIA-SEC adaptation (anti-confabulation -- BLOQUANT)

What makes this skill investor-grade vs a generic template:

1. **Every LIASCAN capability claim cites `file:line`** (agnostic tree-parser,
   nightly CVE rule-gen pipeline, etc.). A claim with no code backing is
   `UNVERIFIED` and cannot ship.
2. **Every market figure cites source + year.** Unsourced = `UNVERIFIED -- placeholder`.
3. **Competitors separated FR vs international**, each rated
   DIRECT / ADJACENT / NO DIRECT COMPETITOR per capability -- reuse the verified
   per-cluster deep-dives in `_alire/01_DOCUMENTATION/business-plan/competitive/`.
4. **SHIPPED vs ROADMAP split** on every capability (agentic AI analyst =
   ROADMAP; RAG over 754 cyber skills = SHIPPED). Never present roadmap as current.
5. **Honest weaknesses slide mandatory** (single-VPS today, scripts partly
   theoretical until recetted, known bugs) -- consistent with `STRATEGIC_ASSESSMENT.md`.
6. **Reuse the existing corpus** before generating: `STRATEGIC_ASSESSMENT.md`
   (+ `_FR`), `CONSOLIDATED.md`, the 10 cluster folders. Do not re-derive what is
   already verified there.

## VERIFICATION GATE (BLOQUANT)

Apres production, AVANT de declarer termine :
- [ ] Chaque claim capability cite un `file:line` reel (Grep verifie l'existence)
- [ ] Chaque figure marche cite source + annee (zero nombre nu)
- [ ] Zero tag `UNVERIFIED` non signale a l'utilisateur dans le livrable final
- [ ] Concurrents separes FR / international, verdict par capability present
- [ ] SHIPPED vs ROADMAP explicite sur chaque capability
- [ ] Si export pptx : QA visuelle passee via `/pptx-recette` (pas de slide vide /
      texte tronque)
- [ ] PLAN_*.md cloture (Status TERMINE) + decision_log alimente

Si une gate echoue : STOP, corriger, re-gate. JAMAIS declarer "termine" avec une
gate rouge ou un nombre non source.

## Scoring agentique (auto-evaluation en fin de workflow)

| Critere | Description | Score |
|---------|-------------|-------|
| C1 Decomposition | Sous-taches identifiees + dependances au demarrage | /10 |
| C2 Planification | PLAN_*.md cree, suivi etape par etape, cloture | /10 |
| C3 Replanification | /replan sur 2+ echecs ; zero invention de donnee | /10 |
| C4 Outillage | Outils choisis dynamiquement (corpus avant web, Edit vs Write) | /10 |
| C5 Tracabilite | decision_log alimente + RETEX si < 40 | /10 |

Score total : /50 -- >= 40 Exemplaire | 30-39 Acceptable | < 30 RETEX obligatoire.
