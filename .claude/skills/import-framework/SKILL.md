---
name: import-framework
description: Importe un referentiel de conformite externe (YAML structuree, PDF officiel, ou structure custom) dans LIA-SEC avec generation automatique des fichiers survey JSON, migration SQL PostgreSQL, mappings inter-referentiels (ISO 27001, ANSSI, NIS2/ENISA 2024/2690), et integration backend Go. Locale EN par defaut (R8 UI Help English Only). Se declenche sur "/import-framework", "importe ce referentiel", "ajoute ce framework", "integre ce standard", "charge ce referentiel", "nouveau referentiel compliance", "transpose ce referentiel". Supporte les sources YAML structurees (avec URN et requirement_nodes), PDF officiels, et structures custom.
---

# Import Framework -- Referentiel de conformite vers LIA-SEC

Importe un referentiel de conformite externe dans l'ecosysteme LIA-SEC (PostgreSQL + Go + React).
Produit automatiquement les fichiers survey JSON, la migration SQL, les mappings vers ISO 27001,
ANSSI et NIS2/ENISA, et le code Go d'integration.

**Avant de commencer, lire :** `references/lia-sec-compliance-infra.md` (schema tables, formats JSON, code Go a modifier)

## Arguments

- `$ARGUMENTS[0]` - Source : chemin local vers YAML/PDF, ou URL GitHub
- `$ARGUMENTS[1]` - Code court : `{CODE}`, `DORA`, `CCB_CFF`, etc. (alphanum + underscore)
- `--locale=en` - Locale du referentiel (defaut: `en`, conforme R8)
- `--skip-mappings` - Ne pas generer les mappings inter-referentiels
- `--dry-run` - Analyser sans ecrire de fichiers
- `--clean-room` - Rephrase clean-room AGPL (RETEX NIST Tier 1 2026-05-26). Active 1b.0ter, anti-clone gate Phase 2.6, metadata provenance Phase 4.1.
- `--retrofit` - Sous-mode RETROFIT (RETEX W3 2026-05-28). Le framework existe deja en DB avec des questions hand-authored mais en schema THIN (sans `cross_reference` / `composite_obligation` / `source_paragraph`). Enrichit en place vers le schema strict + ajoute la profondeur de couverture manquante. Voir "SOUS-MODE RETROFIT" ci-dessous.

---

## SOUS-MODE RETROFIT (`--retrofit`, RETEX W3 2026-05-28)

Realite mesuree : la plupart des frameworks "a densifier" ont DEJA des questions
hand-authored audit-voice, mais en schema THIN (pre-strict). Le travail est ~80%
RETROFIT (enrichir en place) + ~20% net-new (profondeur). Ne PAS re-importer
from scratch ; ne PAS re-authorer les titres existants (ils sont bons).

Workflow retrofit (reutilise par HIPAA/ANNEX_NIS2/PCI/DORA/EU_AI_ACT W3) :

1. **Dump** les questions existantes depuis la DB (avec part grouping) vers
 `data/<code>_full_dump.json`.
2. **Baseline** : appliquer la taxonomie 1.4bis. Si le `reference` herite
 sur-compte, le corriger (1.4ter). Declarer dans PLAN.md.
3. **Builder** `tooling/build_<code>_strict.py` (template reutilisable, ~90%
 identique entre frameworks) :
 - `q()` shape strict + `OPTIONS_STD` 6-niveaux + `EVIDENCE_POLICY_STD`
 - `XREF` : dict de blocs `cross_reference` 5-target par FAMILLE
 (chapitre/requirement/theme), avec `absence_justified` honnete la ou une
 cible est hors-scope (ex: NIS2/HIPAA sur obligations AI-safety ; NIS2 = self
 pour ANNEX_NIS2). Cibles ancrees aux crosswalks publies (NIST 800-66r2,
 ISO Annex A, ENISA), confidence 0.55-0.95.
 - `enrich(q)` : ajoute `composite_obligation` + `source_paragraph` +
 `control_reference` + `evidence_expected[>=2]` + `cross_reference` a CHAQUE
 question existante (preserve le titre).
 - `split_q()` : questions net-new de profondeur, ancrees a un sous-point REEL
 du texte source committe (Phase 2.4 STRONG_SPLIT + 2.4quater expert-implied).
 - emit : config part files (clean) + `unified_mappings.json` (5-target +
 metadata absence_justified) + `composite_audit.json` (LISTE) +
 `data/<code>_questions.json` (flat, pour coverage_gate) + migration Pattern A
 R27 (DELETE+INSERT).
4. **STALE CONFIG** (BLOQUANT) : supprimer TOUS les `config/survey/frameworks/<CODE>/*_part*.json`
 stale (anciens parts dupliques / sous-sections) AVANT d'ecrire le set strict.
 verify_evidence lit les fichiers CONFIG pour les gates voix/composite/quality
 et la DB pour les gates count/coverage -- un desync config/DB fait lire un
 count fantome. Le rebuild doit aligner config = DB = le set strict.
5. **Gates** : `coverage_gate.sh <CODE>` PASS + `verify_evidence.sh <CODE>` 13/13.
6. **Commit** : safe_commit staging explicite, zero foreign (R28), + INDEX + RETEX.

---

## REGLE DE COUVERTURE -- NON-NEGOCIABLE (RETEX 2026-05-26)

**INTERDIT de reduire le nombre de questions assessables vs la baseline.** Le
clean-room AGPL est un changement de TEXTE, pas un changement de SCOPE. Si la
legacy DB porte 462 questions sur 42 articles, le clean-room en porte
**>= 462** (ratio >= 0.9 du baseline). Reduire = perdre de la couverture audit.

Incident declencheur 2026-05-26 (W2A-W2E.1) : 8 frameworks importes avec
40-76% de couverture vs legacy (SOC2 40%, EU_AI_ACT 47%, ANNEX_NIS2 48%,
ISO 50%, DORA 54%, PCI 58%, CIS 76%, HIPAA pre-expansion 67%). Le gate
anti-clone disait PASS (texte different) tandis que la couverture
s'effondrait silencieusement. L'utilisateur (a juste titre) : "pourquoi
systematiquement tu enleves des questions ?? les gates sont pas ok !!!!"

**Cause racine** : Phase 1.4 GATE 1.4 (`assessables_lia >= assessables_reference`)
existait dans le texte de la skill mais N'ETAIT PAS WIREE dans une recette
executable. Seul Jaccard tournait.

**Fix bloquant (2026-05-26)** :

| Phase | Gate | Script | Verdict |
|-------|------|--------|---------|
| 1.4 | Baseline declared in PLAN.md | grep `assessables_legacy` / `assessables_reference` | BLOQUE si baseline absente |
| 2.6bis | Coverage ratio | `bash scripts/coverage_gate.sh {CODE}` | PASS >= 0.9, WARN 0.7-0.9, FAIL < 0.7 |
| 6 | Coverage report committed | `data/coverage_report.json` present | BLOQUE Phase 7 si FAIL |

Reduction acceptable UNIQUEMENT avec `--justified "<raison precise>"`
(ex: "scope restreint aux obligations entite ; sub-acts deferred to W2E-2"),
enregistree dans `coverage_report.json` et citee dans le RETEX. Une
justification " legacy inflated count" est REFUSEE -- the legacy import est inflated
PAR VERBATIM SUB-PARAGRAPH RECITATION, qui est exactement la granularite
Phase 2.4 STRONG_SPLIT recommande. Le fix est de splitter chaque sous-point
(a)/(b)/(c)/(i)/(ii)/(iii) en sous-question hand-authored, JAMAIS de
consolider en une umbrella question.

Pattern STRONG_SPLIT obligatoire pour atteindre la couverture :

```python
# AVANT (FAIL coverage, 1 Q pour 5 sous-points)
Q("Art9.2", "Article 9(2)", "Does the RMS identify, analyse, evaluate and treat ICT risks per points (a)-(d)?")

# APRES (PASS coverage, 4 Qs pour les 4 sous-points)
Q("Art9.2.a", "Art 9(2)(a)", "Does the RMS identify and analyse known and reasonably foreseeable risks...?")
Q("Art9.2.b", "Art 9(2)(b)", "Does the RMS estimate and evaluate risks under intended purpose and foreseeable misuse?")
Q("Art9.2.c", "Art 9(2)(c)", "Does the RMS evaluate other arising risks from post-market monitoring data?")
Q("Art9.2.d", "Art 9(2)(d)", "Does the RMS adopt targeted risk management measures to address identified risks?")
```

---

## AGENTIC LOOP (OBLIGATOIRE pour chaque sub-task)

Chaque sub-task DOIT passer le cycle complet avant de continuer :

OBJECTIVE -> DECOMPOSE -> PLAN -> ACT -> OBSERVE -> EVALUATE -> (REPLAN si echec) -> LOOP ou COMPLETE

### Phase agentique 0.1 -- DECOMPOSE (APRES pre-flight Phase 0)

Apres pre-flight pass, decomposer le travail en sous-taches typees :

```
Decomposition

Objective: import framework {CODE}
Sub-tasks:
1. [TRIVIAL] source detection + extraction inventaire -- depends on: none
2. [MODERATE] proof-of-research + texte officiel telecharge -- depends on: #1
3. [COMPLEX] conversion YAML/PDF -> JSON parts -- depends on: #2
4. [MODERATE] mappings ISO/NIS2/ANSSI -- depends on: #3
5. [MODERATE] migration SQL + load DB -- depends on: #4
6. [COMPLEX] verification gate (verify_evidence.sh PASS) -- depends on: #5
7. [TRIVIAL] livraison + scoring agentique -- depends on: #6
```

### Per-sub-task: PLAN / ACT / OBSERVE / EVALUATE

Chaque sub-task produit AVANT execution :
- Goal (1 phrase)
- Tools (+ raison)
- Expected output
- Success criteria (mesurable)
- Failure signal (declenche REPLAN)

Chaque sub-task produit APRES execution :
- Result (factuel)
- Expected vs actual
- Status: SUCCESS | PARTIAL | FAILURE

### Working Memory Update (obligatoire entre phases principales)

Apres CHAQUE phase principale (0, 1, 1b, 2, 2.6, 3, 4, 5, 5b, 6, 6bis, 7), afficher :

```
Working Memory Update
Completed: [phase ids]
Current: phase N
Pending: [phase ids restants]
Key findings: {important}
Blockers: {si any}
```

### REPLAN formalise (sur FAILURE)

Sur FAILURE d'une sub-task :

```
Replan -- sub-task N
Failure cause: {diagnose}
Alternatives:
 A. {approche A} -- rejected because {raison}
 B. {approche B} -- selected because {raison}
 C. {approche C} -- fallback si B echoue
New plan: {steps mis a jour}
```

INTERDIT de re-tenter l'action exacte qui a echoue. Toujours changer >= 1 variable (tool, parametres, source, approche).

### Escalade

Apres 3 REPLAN sur la meme sub-task -> STOP et escalader a l'utilisateur. INTERDIT :
- boucler silencieusement
- declarer "partiellement OK" sans lister precisement ce qui manque
- skipper la sub-task et continuer

---

## MODELE D'EXECUTION -- Claude inline (RETEX 2026-05-26, Tier 1 NIST)

**Hand-authored = Claude dans la conversation, pas d'API externe.** L'utilisateur a explicitement banni les LLM tiers (Grok / OpenAI / Mistral) pour la generation de questions et le rephrase clean-room :

> "arrete avec grok : tu le fait toi"
> "mais je comprend pas ce qui se passe : pourquoi tu le fait pas ici ?"

REGLES (BLOQUANTES) :
1. **Le rephrase audit-team-voice (clean-room AGPL) est ecrit par CLAUDE dans la
 conversation, jamais via call API externe.** Le tooling Python ne fait QUE :
 merge fragments JSON -> migration SQL -> validation Jaccard. Le contenu des
 questions vient de la conversation -- pas de `curl api.x.ai/grok` ni equivalent.
2. **Exception : "sauf si Claude est pas dispo OU que l'utilisateur cite explicitement Groq/Grok/OpenAI/Mistral".** Si l'utilisateur dit "utilise Groq",
 OK. Sinon : Claude.
3. **Lieux du rephrase :** dans la conversation (Edit/Write a un fichier
 `data/ai_rephrased/{family}.json`) ou directement dans un Python heredoc qui
 compile les questions ecrites par Claude. JAMAIS un appel API masque.
4. **Cas LIA-SEC interne :** si une etape veut un LLM (ex: enrichissement RAG,
 draft initial), passer par `ExecuteWithRAG` (R22) qui route via la fallback
 chain LIA-SEC (Groq P1 -> Ollama P2 -> Claude P4), JAMAIS hardcode.

Incident declencheur : Tier 1 NIST 2026-05-26, 2350 questions hand-authored par
Claude inline pour eliminer la contamination AGPL des questions legacy-derived,
sans aucun appel API externe.

---

## TRACABILITE AGENTIQUE (OBLIGATOIRE)

### Sous-repertoire dedie par projet (OBLIGATOIRE, layout normalise)

Chaque import / projet de revision a UN sous-repertoire qui contient **TOUS** ses
artefacts en sous-dossiers logiques. RIEN n'est eparpille a la racine de
`_alire/tracking/` ni a la racine du dossier projet :

```
_alire/tracking/import-frameworks/{CODE}/ # 1 framework importe
 PLAN.md
 PROOF_OF_RESEARCH.md
 INVENTORY.md
 ARTICLES_VERBATIM.md
 sources/ # source brute committee + manifest.json (sha256 replay-verifiable)

_alire/tracking/<programme>/ # programme transverse multi-frameworks
 PLAN.md
 tooling/ # scripts Python/Bash reutilisables
 recettes/ # scripts de recette (audit_titles.py etc.)
 sources/ # source brute committee par framework (*_source.yaml + manifest)
 data/ # artefacts genere/cache (gitignore les gros JSON/SQL via data/.gitignore)
 reports/ # rapports markdown (audit, rebaseline, RETEX)
```

REGLES (BLOQUANTES) :
- Le `PLAN.md` vit DANS le sous-repertoire, pas a la racine de `_alire/tracking/`.
- **JAMAIS** de nouveau fichier `PLAN_*.md` ou `RETEX_*.md` directement a la racine
 de `_alire/tracking/` (vrac historique des autres sessions = a NE PAS imiter).
- AUCUN script Python / SQL / fichier executable a la racine du sous-repertoire :
 scripts vivent dans `tooling/`, recettes dans `recettes/`.
- Artefacts generes/lourds (gros JSON, SQL bulk) : `data/` + `data/.gitignore`
 (regenerable via tooling/, R31).
- Ajouter UNE ligne pointeur dans `_alire/tracking/INDEX.md` vers le sous-repertoire
 du projet (pas un dump des fichiers internes).

### Source evidence persistante (OBLIGATOIRE -- jamais dans _alire/temp/)

Toutes les **donnees de base** (texte source officiel, PROOF_OF_RESEARCH, texte
verbatim, PDF officiel, sha256 par source) vivent dans le sous-repertoire dedie
ci-dessus, COMMITEES.

**INTERDIT** de mettre la source de verite dans `_alire/temp/` (R7 : temp est wipe,
on perd la tracabilite). `_alire/temp/` = tentatives de download intermediaires /
jetables uniquement. Des qu'une donnee est validee comme source de verite, la copier
dans `import-frameworks/{CODE}/sources/`.

Si la source officielle bloque le download automatique (ex: SDAIA HTTP 403 /
connection reset) : documenter le blocage dans PROOF_OF_RESEARCH.md, extraire le
verbatim depuis des mirrors autoritatifs (jamais inventer), et noter dans
`sources/manifest.json` la methode de capture + l'URL mirror + le sha256 obtenu.

#### REGLE BLOQUANTE -- preuve replay-verifiable (le fichier source brut, PAS seulement son sha256)

Incident recurrent (signale plusieurs fois par l'utilisateur, 2026-05-23 : DK / HR /
RO importes avec `sha256` dans `manifest.json` MAIS sans le fichier source brut commite).
Un sha256 dans le manifest qui ne pointe sur AUCUN fichier commite n'est PAS une preuve :
il est impossible de re-verifier (`sha256sum fichier == manifest`). C'est exactement le
trou que cette regle ferme.

OBLIGATOIRE pour CHAQUE entree `sources[]` du manifest :

1. **Le fichier source EXACT sur lequel le sha256 a ete calcule DOIT etre commite**
 dans `import-frameworks/{CODE}/sources/` (PDF, HTML, ou .txt d'extraction -- l'artefact
 reellement hashe, pas une variante). Le champ `filename`/`file` du manifest DOIT
 pointer sur ce fichier commite (jamais `null`, jamais `NOT_DOWNLOADED`).
2. **Replay-verifiable** : `sha256sum sources/<file>` DOIT redonner exactement le
 `sha256` du manifest. C'est le seul test de preuve valable.
3. Le fichier source vit dans `sources/` (COMMITE), jamais uniquement dans `_alire/temp/`
 (wipe). Des qu'un download est valide, le COPIER dans `sources/` AVANT le commit.
4. **Si la source officielle a derive depuis la capture** (page dynamique re-fetch != sha
 original, ex: portails JS qui wrappent le texte legal) : committer la capture
 disponible + un `sources/SOURCE_NOTE.md` qui declare les DEUX sha (original capture vs
 re-fetch), explique la derive, et confirme que le VERBATIM provient de la capture
 originale. Transparent, jamais de faux sha.
5. Le verbatim de `ARTICLES_VERBATIM.md` DOIT etre derivable du fichier source commite
 (pas d'un fichier disparu). Si la seule source est un texte extrait, c'est CE texte
 extrait qui est hashe et commite.

### Decision log
Logger dans `_alire/02_LOGS/Journals/decision_log.jsonl` :
- Format source detecte (YAML structuree, PDF, custom)
- Strategie de decoupage en parts (par objectif, par domaine, par profondeur)
- Mappings generes et leur methode (extraction directe, inference, recherche)
- Alternatives rejetees (pourquoi tel decoupage, tel mapping_type)

### Action Journal (append-only, OBLIGATOIRE par phase)

Chaque phase principale (0, 0.1, 1, 1b, 2, 2.6, 3, 4, 5, 5b, 6, 6bis, 7) DOIT logger une ligne dans `_alire/02_LOGS/Journals/action_journal.jsonl` :

```
{"ts":"ISO8601","skill":"import-framework","framework":"{CODE}","phase":"N","action":"verb","tool":"name|none","input":"summary","output":"summary","status":"success|partial|failure","decision":"what_decided"}
```

Le journal sert : audit (qui a fait quoi) + debug (chaine complete sur incident) + supervision (l'utilisateur peut interrompre/rediriger). Append-only -- jamais editer une ligne posee.

### Replanification
Si 2 etapes echouent consecutivement, INVOQUER `/replan`. Voir AGENTIC LOOP > REPLAN formalise pour le format obligatoire (diagnose + A/B/C + escalade apres 3 cycles).

### Scoring agentique (auto-evaluation en fin de workflow)

| Critere | Description | Score |
|---------|-------------|-------|
| 1. Decomposition | Le referentiel a-t-il ete decompose en sous-taches (extraction, conversion, mappings, integration) ? | /10 |
| 2. Planification | Un PLAN_IMPORT_FW_*.md a-t-il ete cree et suivi etape par etape ? | /10 |
| 3. Replanification | Les echecs (parsing, build, SQL) ont-ils declenche une adaptation du plan ? | /10 |
| 4. Outillage dynamique | Les bons outils ont-ils ete choisis (agents YAML, WebSearch pour mappings, SQL direct) ? | /10 |
| 5. Tracabilite | decision_log complet + PLAN_*.md a jour + journal des actions ? | /10 |

**Score total: /50** -- >= 40 : Exemplaire, 30-39 : Acceptable, < 30 : Retex obligatoire

---

## PHASE 0 -- PRE-FLIGHT (BLOQUANT)

Creer le sous-repertoire dedie du projet AVANT tout :

```bash
mkdir -p _alire/tracking/import-frameworks/$CODE/sources
```

Verifier l'environnement avant toute action :

```bash
# PostgreSQL accessible
PGPASSWORD="$LIA_DB_PASS" psql -h localhost -U lia_admin -d lia_scan -c "SELECT COUNT(*) FROM compliance_frameworks" 2>/dev/null

# Code referentiel pas deja pris
PGPASSWORD="$LIA_DB_PASS" psql -h localhost -U lia_admin -d lia_scan -c "SELECT code FROM compliance_frameworks WHERE code = '$CODE'"
# -> Si existe : STOP, demander confirmation ecrasement

# Repertoire survey pas deja existant
ls config/survey/frameworks/$CODE/ 2>/dev/null
# -> Si existe : STOP, backup avant ecrasement
```

Si un pre-flight echoue : STOP, corriger AVANT de continuer.

---

## PHASE 1 -- EXTRACTION (analyser la source)

### 1.1 Detecter le format source

| Format | Detection | Action |
|--------|-----------|--------|
| YAML structuree | `urn: urn:framework:risk:library:*` | Parser YAML, extraire `requirement_nodes` |
| PDF officiel | `.pdf` | OCR + extraction structuree (sections, articles) |
| JSON custom | `.json` avec `questions[]` ou `controls[]` | Mapper directement |
| URL GitHub | `github.com/` | Cloner/fetch puis detecter format |

### 1.2 Extraire la structure

Pour chaque source, produire un inventaire intermediaire :

```
=== INVENTAIRE REFERENTIEL ===
CODE : {code}
NOM : {nom complet}
VERSION : {version}
LOCALE : fr
PROVIDER : {editeur}
CATEGORIE: regulatory | framework | standard | guide

STRUCTURE :
 Objectifs/Domaines (niveau 1) : N
 Sous-categories (niveau 2) : N
 Exigences evaluables : N
 Total nodes : N

GROUPES D'IMPLEMENTATION : [liste si applicable]
```

### 1.3 GATE utilisateur

Presenter l'inventaire. Demander validation AVANT de continuer.

### 1.4 Benchmark de granularite (calibrage de richesse)

Un import "mince" (1 question = 1 article haut-niveau) sous-evalue souvent le
referentiel. AVANT conversion, etablir une cible de richesse :

1. **Compter les noeuds ASSESSABLES d'une reference publique** si elle existe
 (YAML communautaire structuree, autre outil GRC). Distinguer en-tetes
 (`assessable: false`) des items repondables (`assessable: true`). Ne JAMAIS
 copier le contenu (R13 + clean-room) -- seulement compter pour calibrer.
2. **Cible LIA-SEC = egaler ou depasser** ce compte d'assessables, par
 decomposition fidele au texte officiel (sous-paragraphes, sous-points
 mandatoires -- voir Phase 2.4), jamais par invention de questions.
3. **Documenter dans INVENTORY.md** : `assessables_reference={N}` vs
 `assessables_lia={M}` avec `M >= N` justifie par les sous-points splittes.

Incident declencheur 2026-05-24 (CER 17 questions initiales) : l'utilisateur a
juge le 2e questionnaire trop maigre. Cause : CER = directive haut-niveau, la
plupart des obligations pesent sur les Etats-membres. Fix : decomposer chaque
obligation ENTITE en sous-questions verbatim (Art 13(1)(a-f) -> 8 questions) ->
30 assessables > 17 de la reference. Le benchmark de granularite rend ce
calibrage systematique au lieu de reactif.

GATE 1.4 (BLOQUANT) : declarer DANS `PLAN.md` les deux lignes :

```
assessables_legacy: <N> # legacy DB assessable count
assessables_reference: <N> # external public reference count (NIST OLIR, public YAML, etc.)
```

Sans ces lignes, le coverage gate Phase 2.6bis ne peut pas fonctionner et la
recette refuse de continuer (exit 2). Mesurer les deux baselines AVANT Phase 2
ecriture :

```bash
# legacy DB
DBURL=$(systemctl cat lia-backend | awk -F'=' '/^Environment=DATABASE_URL/{print substr($0, index($0,"=")+1)}' | sed 's/^DATABASE_URL=//')
psql "$DBURL" -tAc "SELECT COALESCE(SUM(jsonb_array_length(questions)),0) FROM compliance_frameworks cf JOIN framework_surveys fs ON fs.framework_id=cf.id WHERE cf.code='${CODE}';"

# external reference (selon source)
# - NIST OLIR / OSCAL : compter les controles + sub-controls de l'archive
# - YAML public (legacy YAML fork) : `grep -c 'assessable: true' source.yaml`
# - HTML OJ EUR-Lex : compter Articles + sous-paragraphes (a)/(b)/(c)
```

Si `assessables_lia < max(legacy, reference) * 0.9`, STOP et soit :
1. **Splitter les sous-points (Phase 2.4 STRONG_SPLIT)** pour atteindre la cible -- approche par defaut.
2. **OU** declarer explicitement `--justified "<raison precise>"` dans la
 recette coverage_gate Phase 2.6bis, raison enregistree dans `coverage_report.json`
 et citee dans le RETEX final.

INTERDIT (RETEX 2026-05-26) : declarer "legacy inflated count" comme
justification. Ce n'est PAS une justification -- c'est exactement la
granularite que Phase 2.4 STRONG_SPLIT impose. Verbatim sub-paragraph
recitation dans l'import legacy = granularite legitime ; il faut REPRODUIRE cette
granularite avec du texte hand-authored, pas consolider.

#### 1.4bis EXCLUSION TAXONOMY -- ce qui N'EST PAS une obligation assessable (RETEX W3 2026-05-28)

Incident W3 : 4 frameworks avaient un `assessables_reference` gonfle 3-5x parce
qu'il comptait des artefacts NON-obligatoires comme des obligations. Resultat :
coverage gate FAIL contre une cible fausse, et la "remediation" naive aurait
FABRIQUE ~1000 questions bidons (exactement le bullshit que l'utilisateur a
challenge). Le `reference` DOIT compter UNIQUEMENT les obligations auditables sur
l'ENTITE EVALUEE, et EXCLURE :

| A EXCLURE du baseline | Exemple | Pourquoi |
|-----------------------|---------|----------|
| **Items illustratifs / non-mandatoires** | SOC2 Points of Focus ; listes `such as` / `for example` / `including but not limited to` | EXAMPLE_LEAD (Phase 2.4) -- pas des exigences |
| **Etapes de verification** | PCI testing procedures (.a/.b) | C'est COMMENT l'assesseur verifie -> va dans `evidence_expected`, pas une obligation separee |
| **Paragraphes diriges vers l'autorite / un tiers** | "the ESAs shall...", "the competent authority shall...", "the Commission shall adopt..." (DORA Ch VII-IX, AI Act gouvernance/notified bodies) | L'entite evaluee n'a aucun controle dessus |
| **Penalites, dispositions finales/transitoires, recitals, definitions, scope** | AI Act Art 99-101, DORA Art 57-64 | Pas des controles auditables |

**Regle de comptage qui marche** : grep le VERBE D'OBLIGATION dirige sur l'entite
(`financial entities shall`, `providers shall`, `covered entity shall`, `relevant
entities shall`, `the controller shall`). Ce compte = le plancher d'obligations.
Les sous-points (a)/(b)/(c) de CES obligations = la profondeur STRONG_SPLIT.

Baselines reels verifies W3 (vs les sur-comptes) : SOC2 61 critères (pas 187 PoF) ;
PCI 205 defined-approach requirements (pas 355 testing procedures) ; DORA ~90
obligations entite (pas 500) ; EU_AI_ACT ~150 obligations entite (pas 868).

#### 1.4ter CHEMIN SANCTIONNE de CORRECTION d'un baseline SUR-compte (RETEX W3)

Le 1.4 ci-dessus interdit le "inflated count" comme excuse pour SOUS-couvrir. Mais
il faut un chemin pour le cas INVERSE : un `reference` herite qui SUR-compte. Si le
`reference` declare compte des artefacts non-obligatoires (selon la taxonomie 1.4bis),
le CORRIGER VERS LE BAS est legitime et OBLIGATOIRE :

1. Recompter le baseline = obligations entite reelles (verbe d'obligation entite).
2. Documenter la correction dans `PLAN.md` (garder l'ancien chiffre en
 `assessables_reference_legacy_overcount: <N>`) + `coverage_report.json` + le
 message de commit, avec la justification factuelle scope-article (quels
 articles/items exclus et pourquoi).
3. C'est DISTINCT du "inflated count hand-wave" interdit : ici on ne consolide pas
 des sous-points mandatoires, on retire des NON-obligations (PoF illustratifs,
 testing procedures, articles autorite, penalites, recitals).

Precedents W3 : SOC2 187->61, PCI 355->205, DORA 500->90, EU_AI_ACT 868->150.

---

## PHASE 1b -- PROOF OF RESEARCH (WebSearch OBLIGATOIRE)

Avant de convertir, VALIDER la source par une recherche internet. Cette phase est **NON NEGOCIABLE**.

### 1b.0 ANTI-CONFABULATION -- texte legal = source officielle UNIQUEMENT (BLOQUANT)

**INTERDIT ABSOLU d'improviser ou de deriver le contenu des articles depuis des
mirrors/blogs/resumes/commentaires juridiques tiers.** Le mapping article -> contenu
DOIT venir du texte officiel telecharge et lu.

Incident declencheur 2026-05-23 (KSA_PDPL) : le texte des articles a ete extrait de
mirrors secondaires (saudiprivacylaw.com) qui avaient un decalage systematique
article->contenu. Le questionnaire genere mappait Art 5 = "collection from third
party", Art 13 = "security measures", Art 18 = "breach notification" -- TOUS FAUX.
Le PDF officiel SDAIA dit : Art 5 = consent, Art 13 = inform-at-collection,
Art 18 = destruction/retention. 28 questions confabulees chargees en prod avant
detection. L'utilisateur (a juste titre) : "tu as confabule, ne refais plus ca".

REGLE :
1. **Telecharger le document officiel.** Si l'autorite bloque le download direct
 (curl 56 / WebFetch socket / 403), NE PAS abandonner apres 2 essais. Epuiser les
 methodes (Bloc 2) :
 - `wget`/`curl` avec User-Agent navigateur reel + Accept header
 - **archive.org wayback** : `curl -sSL "https://web.archive.org/web/2id_/<URL>"`
 (a fonctionne pour SDAIA quand le serveur direct bloquait)
 - CDX pour lister les snapshots : `http://web.archive.org/cdx/search/cdx?url=<host/path>*&output=text&fl=timestamp,original,statuscode,length`
 -> choisir un snapshot `200` avec une `length` realiste (pas 500-800 octets = page d'erreur)
 - gazette officielle / Bureau of Experts (boe.gov.sa, eur-lex, legifrance, etc.)
 - Playwright `browser_navigate` (vrai navigateur) en dernier recours
2. **Verifier que le PDF telecharge est COMPLET** : compter les articles reels
 (`file` = page count ; lire le dernier article = doit etre la clause finale
 d'entree en vigueur, pas un article du milieu). Un PDF tronque (ex: 8 pages /
 Art 1-18 alors que la loi en a 43) est INCOMPLET.
3. **Lire le texte officiel** (Read tool sur le PDF = rendu visuel fiable ;
 `pdftotext -layout` peut desordonner le multi-colonne -> preferer Read visuel).
4. **Si le texte officiel complet est INTROUVABLE ou INCOMPLET** : STOP. Presenter
 a l'utilisateur ce qui est confirme vs manquant. NE JAMAIS combler les trous avec
 du contenu de mirror/commentaire. Pas de questionnaire genere sur du texte non
 officiel.
5. **Tracer chaque article** : source_url officielle + sha256 du PDF dans
 `sources/manifest.json`. Les mirrors juridiques servent UNIQUEMENT a localiser
 l'URL officielle, jamais comme source du texte.

GATE 1b.0 : aucune Phase 2 (conversion) tant que le texte officiel complet n'est pas
telecharge, lu, et son mapping article->contenu verifie article par article.

#### 1b.0-copyright SOURCE SOUS COPYRIGHT non-redistribuable (RETEX W3 2026-05-28)

Certaines normes (PCI DSS, AICPA TSC, ISO, CIS) sont sous copyright et NON
redistribuables. Posture obligatoire :

1. **Committer la source dans le repo PRIVE de tracking** (`import-frameworks/{CODE}/sources/`)
 comme reference d'authoring + preuve sha256 replay-verifiable. Le produit ne ship
 JAMAIS le texte verbatim -- uniquement des questions clean-room audit-voice (R13).
2. `manifest.json` declare la posture licence explicitement (ex: "PCI SSC copyright --
 committed to PRIVATE tracking repo as authoring reference only").
3. **Si AUCUNE source obtenable** (paywall licence, pas de mirror) : la densification
 net-new est BLOQUEE -- NE PAS fabriquer de questions de memoire. Escalader a
 l'utilisateur (comme CIS CC BY-NC-SA). Le retrofit schema des questions EXISTANTES
 reste possible (pas de contenu nouveau).
Incident W3 : PCI initialement bloque (pas de source) -> l'utilisateur a fourni le
PDF v4.0.1 -> committe sha256 -> densification faithful debloquee.

### 1b.0bis CLEAN-ROOM AGPL (sous-mode `--clean-room`, RETEX 2026-05-26)

Quand la version DB legacy d'un framework porte une contamination de licence
(packaging tiers AGPL : legacy-derived, opencontrol-derived, etc.) qui rend la
diffusion LIA-SEC SaaS commerciale risquee, l'objectif n'est pas d'INVENTER mais
de REPRODUIRE en clean-room la semantique du texte officiel (qui, lui, est public
domain pour NIST/CISA/ANSSI ou Crown Copyright reusable pour UK).

Workflow :
1. **Source = texte officiel public domain** committed sous `sources/` (sha256
 replay-verifiable, Phase 1b.0). Le legacy DB AGPL n'est PAS la source -- c'est
 un BENCHMARK de granularite (Phase 1.4) et un reference Jaccard (Phase 2.6),
 jamais le texte source.
2. **Rephrase hand-authored audit-team voice** : chaque question est ecrite par
 Claude dans la conversation, voix British English neutre ("organisation",
 "Has the organisation identified..."), forme question d'auditeur, jamais
 copie verbatim du texte officiel ni du legacy.
3. **DB-as-extracted-source equivalence** : quand le PDF officiel ET le legacy
 DB pointent sur le meme texte normatif (titres de controle identiques), la
 DB legacy peut servir d'extraction de titres SI le PDF officiel est aussi
 commit sous `sources/` avec son sha256. Le sha256 du PDF reste la source de
 verite -- la DB est un raccourci d'extraction, pas la source legale.

### 1b.0ter Provenance + AGPL clearance (BLOQUANT pour `--clean-room`)

Tout import `--clean-room` DOIT documenter dans `sources/PROVENANCE.md` :

| Champ | Contenu |
|-------|---------|
| `source_authority` | "NIST" / "CISA" / "ANSSI" / "ENISA" / ... |
| `license` | "US Government work (17 USC 105) = public domain" / "Crown Copyright reusable" / "EU PSI Directive" / ... |
| `agpl_contamination` | "cleared" si rephrase clean-room termine + Jaccard gate PASS |
| `legacy_replaces` | code du framework legacy supprime (ex: `NIST_800_53_R5`) |
| `replacement_method` | "hand_authored_clean_room" |
| `rephrase_author` | "claude_inline" (jamais "external_llm") |
| `source_sha256` | sha256 du PDF/JSON officiel commit |

GATE 1b.0ter : le commit final DOIT porter ces champs dans `compliance_frameworks.metadata`
(Phase 4.1) sinon clean-room status = ECHEC.

### 1b.1 Recherche du document officiel

Utiliser l'agent `websearch-agent` (`model: "haiku"`) pour :

1. **Trouver le PDF/page officiel** du referentiel (site de l'autorite : ANSSI, ENISA, ISO, CNIL, etc.)
2. **Confirmer la version** : le YAML source YAML correspond-il a la derniere version publiee ?
3. **Identifier les mappings officiels** : l'autorite publie-t-elle des tables de correspondance ISO/NIS2 ?

**Model Selection:** Le websearch-agent utilise `model: "haiku"` (recherche URL + extraction = pas de raisonnement complexe).

Requetes WebSearch suggerees :
```
"{nom referentiel}" site:ssi.gouv.fr OR site:enisa.europa.eu filetype:pdf
"{nom referentiel}" version {version} mapping ISO 27001
"{nom referentiel}" NIS2 directive transposition
```

### 1b.2 Cross-validation

| Verification | Methode | Action si ecart |
|--------------|---------|-----------------|
| Nombre d'exigences | Comparer YAML vs PDF officiel | Signaler a l'utilisateur, logger dans decision_log |
| Version | Comparer version YAML vs derniere version publiee | Proposer update ou continuer avec warning |
| Noms des objectifs | Comparer titres YAML vs titres officiels | Corriger les titres dans le JSON genere |
| Mappings | Comparer mappings YAML vs tables officielles | Prioriser la source officielle |

### 1b.3 Livrable

Produire un bloc `PROOF_OF_RESEARCH` dans le rapport :

```
=== PROOF OF RESEARCH ===
PDF officiel : {URL du document officiel trouve par WebSearch}
Version confirmee: {oui/non} -- ecart: {detail si non}
Exigences check : YAML={N} vs PDF={N} -- {match/ecart}
Mappings officiels: {URL si disponible}
Sources consultees: {liste URLs}
```

Logger dans `decision_log.jsonl` : `action: "PROOF_OF_RESEARCH"`, `outcome: "confirmed|divergence"`.

### 1b.4 GATE

Si divergence significative (version differente, exigences manquantes, structure differente) :
STOP et presenter l'ecart a l'utilisateur AVANT de continuer.

---

## PHASE 2 -- CONVERSION (YAML/PDF -> JSON LIA-SEC)

### 2.1 Creer le repertoire survey

```
config/survey/frameworks/{CODE}/
 {code}_master_config.json
 {code}_part1.json
 {code}_part2.json
 ...
```

### 2.2 Regles de decoupage en parts

- **1 part par objectif/domaine de niveau 1** (max 20 questions par part)
- Si un domaine a plus de 20 questions, le decouper en sous-parts
- Les noeuds `assessable: false` deviennent des `sections`
- Les noeuds `assessable: true` deviennent des `questions`

### 2.3 Format survey JSON (EN par defaut, R8)

**NE PAS INVENTER LE FORMAT.** Lire les fichiers de reference existants AVANT de generer :

```bash
# Lire ces fichiers pour comprendre le format reel (270 frameworks existants) :
config/survey/frameworks/ISO27001_2022/iso27001_2022_master_config.json
config/survey/frameworks/ISO27001_2022/iso27001_2022_part01_context_scope.json
config/survey/frameworks/NIS2_DIRECTIVE/nis2_directive_master_config.json
config/survey/frameworks/ANNEX_NIS2_REGULATION_2024_2690/master_config.json
```

Chaque question dans un part_N.json doit avoir TOUS ces champs :
`id`, `type: "radio"`, `required: true`, `title` (EN), `section`, `control_reference`,
`weight` (1-10), `weight_justification`, `implementation_groups`, `sources[]`,
`preuves_attendues[]`, `options[]` (6 niveaux : fully/largely/partially_implemented, planned, not_implemented, not_applicable),
`cross_reference` (voir 2.4bis).

S'aligner strictement sur le format constate dans les fichiers existants.

#### Distinguer VERBATIM vs AUTHORED vs INFERRED (honnetete, R18)

Trois categories de contenu dans une question. Ne JAMAIS les confondre ni
pretendre que l'AUTHORED/INFERRED vient de la source :

| Categorie | Champs | Origine | Regle |
|-----------|--------|---------|-------|
| VERBATIM | `title`, `control_reference`, `implementation_groups`, niveaux/comptes | Texte officiel telecharge | Tracable mot-pour-mot dans le fichier source commite |
| AUTHORED | `options[]` 6 niveaux, `weight`, `weight_justification`, `preuves_attendues[]` | Echafaudage d'evaluation standard LIA-SEC | Meme pattern que les frameworks existants ; pas un fait source |
| INFERRED | `cross_reference`, mappings (Phase 3) | Rapprochement thematique | confidence 0.6-0.7, labellise inference, jamais "officiel" |

Le RETEX final DOIT declarer ces 3 categories explicitement (l'utilisateur a
demande "tu as rien invente ?" 2026-05-24 -- la reponse honnete distingue fait
verbatim / echafaudage authore / inference labellisee).

### 2.3bis AUDITOR VOICE + COMPOSITE DECOMPOSITION (BLOQUANT, top-level, applicable a TOUS imports)

User feedback recurrent : "prepare les questions comme le ferait un auditeur ; on fait pas 1 pour 1 des items de framework si 1 item sous-entend plusieurs choses".

Cette regle s'applique a TOUS les imports (pas seulement `--clean-room`).

#### Regle 1 -- VOIX D'AUDITEUR (pas description normative)

Chaque question DOIT etre ecrite comme une question d'audit (interrogative, verifiable, evaluable), JAMAIS comme une copie du texte normatif officiel.

| INTERDIT (description normative) | CORRECT (question d'auditeur) |
|---------------------------------|-------------------------------|
| "The organisation shall implement access controls." | "Has the organisation implemented documented access controls covering provisioning, review, and revocation?" |
| "Mesures de chiffrement au repos." | "Does the organisation enforce encryption at rest for data classified as sensitive, with documented key management?" |
| "Incident reporting within 24 hours." | "Has the organisation defined and tested an incident reporting procedure that meets the 24-hour notification window?" |

Pattern : `Has the organisation...?` / `Does the organisation...?` / `Are ... documented and tested?`. Forme operationnelle, sujet=organisation, verbe perfect/present, fin par `?`.

Ce n'est PAS une option esthetique. Une copie verbatim normative = inutilisable en audit (l'auditeur ne sait pas quoi cocher) + risque de clone Jaccard (Phase 2.6 FAIL).

#### Regle 2 -- COMPOSITE DECOMPOSITION (1 item framework -> N questions)

Un item de framework (article, controle, exigence) DOIT etre decompose en N questions SI il porte >=1 des signaux COMPOSITE suivants :

| Signal COMPOSITE | Exemple | Action |
|------------------|---------|--------|
| **>=2 obligations distinctes verifiables** | "shall identify, classify and protect assets" -> 3 obligations | 3 questions (1 par obligation verifiable) |
| **liste de sujets multiples** | "policies, procedures, controls and training" | 1 question par sujet |
| **mixe process + evidence + responsibility** | "designate a responsible owner, maintain a register, review annually" | 3 questions (owner, register, review) |
| **enumeration normative (i/ii/iii, a/b/c)** | "shall include the following: (a)... (b)... (c)..." | STRONG_SPLIT Phase 2.4 |
| **conjonctions normatives** | "and shall also" / "moreover" / "in addition" reliant obligations | 1 question par segment |

REGLE 1-pour-1 INTERDITE si signal COMPOSITE detecte. Une copie 1->1 d'un article multi-obligation = questionnaire inutilisable (l'auditeur ne peut pas evaluer plusieurs choses dans 1 reponse).

#### Garde-fous anti-inflation (RETEX DORA 2026-05-25)

L'inflation a l'inverse est aussi interdite. Un agent sonnet sans gate strict peut produire 3 sub-q/exigence par defaut = x4 explosion (DORA 208 -> 970 = inutilisable).

| Garde-fou | Regle |
|-----------|-------|
| Default sub_q | 0 (pas de split par defaut) |
| Max sub_q par item | 3 (au-dela = re-evaluer si l'item est trop large) |
| Justification COMPOSITE | OBLIGATOIRE par split : citer le signal exact qui a declenche le COMPOSITE |
| Verbatim heritage | Chaque sous-question porte le texte verbatim du segment normatif correspondant, jamais paraphrase |

#### GATE 2.3bis (bloquante)

Avant Phase 4 (chargement DB), verifier :

1. **VOIX**: aucune question commence par "The organisation shall" / "L'organisation doit" (= description, pas question). Doit commencer par `Has`, `Does`, `Are`, `Is`, `Have`, ou equivalent interrogatif.
2. **COMPOSITE**: pour chaque item framework avec >=2 obligations distinctes, le compte de questions >= 2. Logger en JSON `data/composite_audit.json` : `{control_ref, signal, n_obligations, n_questions, justification}`.
3. **PLAFOND**: 0 item avec > 3 sub-questions sans justification explicite dans `composite_audit.json`.

Script de gate (template) :

```bash
# .claude/skills/import-framework/scripts/audit_voice_composite.py {CODE}
# Exit 0 = OK
# Exit 1 = FAIL (voice description + N items sans split COMPOSITE)
```

`FAIL` -> retour Phase 2 conversion. Pas de progression vers DB tant que GATE 2.3bis pas verte.

Incident declencheur permanent : utilisateur insiste plusieurs fois "comme un auditeur", "pas 1 pour 1". Cette gate ferme la classe de defaut au lieu de la relever en RETEX.

### 2.4 Split des sous-points (granularite fidele)

Un controle/article avec des sous-points enumeres (i/ii/iii, a/b/c) peut etre
soit une LISTE D'EXIGENCES (chaque sous-point est obligatoire et evaluable
separement), soit une LISTE ILLUSTRATIVE (exemples non exhaustifs). Le split
depend du signal lexical :

| Signal | Categorie | Action |
|--------|-----------|--------|
| `the following controls`, `as follows`, `shall include the following`, `must implement`, `: ` suivi d'enumeration normative | STRONG_SPLIT | 1 question chapeau + 1 sous-question verbatim par sous-point |
| `such as`, `for example`, `e.g.`, `including but not limited to`, `for instance` | EXAMPLE_LEAD | garder UNE seule question (liste illustrative, ne pas splitter) |

**STRONG_SPLIT override EXAMPLE_LEAD** : si les deux signaux coexistent dans le
meme controle, le signal normatif gagne. Incident 2026-05-24 (DEFSTAN 2305
"Remote Access - VPN ... for example VPN") : `for example` declenchait
EXAMPLE_LEAD et gardait le controle entier alors que les sous-points etaient
des exigences. Fix = STRONG_SPLIT prioritaire.

Resultat attendu : le compte de questions DEPASSE le nombre de controles bruts
(DEFSTAN 148 controles -> 258 questions assessables > 228 de la reference
publique), sans inventer de contenu -- chaque sous-question porte le texte
verbatim du sous-point.

Chaque sous-question herite du `control_reference` parent suffixe
(`2305`, `2305.i`, `2305.ii`) et du meme `cross_reference`.

### 2.4quater QUESTIONS IMPLICITES D'EXPERT (OBLIGATOIRE, user feedback 2026-05-28)

> "une rule de compliance peut, pour un expert, susciter plusieurs questions qui
> ne sont pas explicites dans la rule mais sous-entendues par celle-ci et connues
> de l'expert auditeur. On doit toujours avoir ca en ligne de mire."

Un controle de conformite ne se limite PAS a son texte verbatim ni a ses
sous-points enumeres (Phase 2.4 STRONG_SPLIT). Un **auditeur cyber expert**
derive d'une seule obligation plusieurs questions IMPLICITES -- non ecrites
mais sous-entendues par l'obligation et connues du metier. Ces questions
implicites sont une source de couverture legitime, AU-DELA du compte de
sous-points verbatim.

**Les axes d'implicite que l'expert doit systematiquement interroger** (pour
CHAQUE obligation, se demander lesquels s'appliquent) :

| Axe implicite | Question d'expert que la regle sous-entend |
|---------------|--------------------------------------------|
| **Operationnalisation** | La mesure est-elle reellement mise en oeuvre (pas seulement documentee en politique) ? |
| **Verification / preuve** | Comment l'organisation PROUVE-t-elle que la mesure fonctionne (echantillon, registre, sign-off) ? |
| **Efficacite / test** | La mesure est-elle testee periodiquement (et pas juste declaree) ? Avec quel resultat ? |
| **Couverture / perimetre** | La mesure couvre-t-elle 100% du perimetre (tous les actifs, tous les flux, tous les tiers) ? |
| **Cas limites / exceptions** | Les exceptions sont-elles tracees, justifiees, re-evaluees (ex: addressable HIPAA, derogations) ? |
| **SLA / delais** | Quand un delai est sous-entendu (revocation, notification, revue), est-il defini et mesure ? |
| **Automatisation** | La mesure repose-t-elle sur un controle automatise verifiable plutot que manuel faillible ? |
| **Bout-en-bout** | Le workflow est-il integre de bout en bout (ex: HR -> IAM -> formation avant acces) ? |

Exemple HIPAA 164.308(a)(1)(ii)(A) Risk Analysis (UNE obligation) -> plusieurs
questions d'expert legitimes :
1. (verbatim) L'analyse de risque est-elle conduite ?
2. (perimetre) Couvre-t-elle TOUTE la population d'actifs ePHI ?
3. (efficacite) Est-elle remise a jour suite a changement majeur / incident ?
4. (preuve) Le resultat alimente-t-il un plan de traitement trace ?

#### Garde-fou anti-confabulation (R4 + R18, NON-NEGOCIABLE)

Une question implicite reste ANCREE sur l'obligation source -- ce n'est PAS de
l'invention :
- chaque question implicite porte le MEME `control_reference` que l'obligation
 qui la sous-entend (ou un suffixe lisible),
- son `source_paragraph` cite l'obligation reelle du texte officiel committe,
- elle interroge une facette RECONNUE du metier d'audit (les 8 axes ci-dessus),
 jamais une exigence absente du referentiel ni une obligation d'un autre cadre,
- INTERDIT : inventer une obligation que le texte ne porte pas, meme implicitement
 (ex: exiger la MFA si le referentiel ne parle que d'"authentification" -- on
 interroge alors l'authentification, pas une techno non citee).

Le test : "un auditeur lisant cette obligation poserait-il honnetement cette
question lors d'un audit ?" Si oui et qu'elle est ancree au texte -> legitime.
Si elle exige quelque chose d'absent du referentiel -> confabulation, INTERDIT.

### 2.4ter ANTI-PARAPHRASE + INTELLIGENCE OBLIGATOIRE (BLOQUANT, RETEX 2026-05-26)

User feedback 2026-05-26 : "tu as fait en sorte que la skill utilise Claude ses connaissances et son intelligence ? plus de paraphrase un vrai questionnement d'auditeur ? un vrai enrichissement ?"

Une **vraie question d'auditeur** N'EST PAS une paraphrase du texte normatif. La paraphrase = wrapper deguise :

- Verbatim normatif : `The controller shall implement appropriate safeguards.`
- PARAPHRASE INTERDITE : `Has the controller implemented appropriate safeguards?` (juste verbe interrogatif + `?` -- AUCUNE valeur d'audit ajoutee)
- AUDIT REEL OBLIGATOIRE : `Are technical and organisational measures documented and tested annually to demonstrate the appropriateness of safeguards under Article 32 -- including encryption, pseudonymisation, access control, and resilience proportionate to the risks?`

#### Definition operationnelle de la paraphrase (detection algorithmique)

Une question est une PARAPHRASE si :
- `lemma_overlap(title, requirement_text) > 70%` (apres suppression stopwords) **ET**
- la question n'ajoute aucun element verifiable absent du verbatim : pas de mention d'artefact concret (procedure, registre, log, evidence), pas de cadence (annuel, semestriel), pas de cite externe (Art 32, RoPA, Art 28, DPIA).

#### Mobilisation des connaissances Claude (per-question, obligatoire)

Pour CHAQUE question, Claude DOIT mobiliser son savoir reel :

1. **Identifier l'obligation evaluable** (pas la phrase normatif) : qu'est-ce qu'un auditeur peut effectivement constater ? (existence d'une procedure, presence d'un artefact, mesure d'une cadence, completude d'un registre).
2. **Cast as audit question** : forme "Does the organisation ... ?", "Has X been documented and ... ?" -- avec une COMPOSANTE de verifiabilite explicitee dans la question.
3. **Ancrer dans le cadre operationnel** : citer l'artefact attendu (registre Art 30, RoPA, DPIA, AIPD, LIA, DPA Art 28, SCC, NPP, BAAs, log, evidence dossier), la cadence (annuel, semestriel, par evenement), ou le test (revue legale, audit interne, audit externe, test de penetration).
4. **evidence_expected non-generique** : INTERDIT "Documentation for requirement X". CHAQUE element doit nommer un artefact concret + son owner + sa cadence ou sa source.
5. **cross_reference rationale non-generique** : INTERDIT "covers privacy obligations". OBLIGATOIRE de citer le numero de controle/article cible + ce qu'il prescrit + pourquoi il correspond/diverge. La `rationale` DOIT mobiliser le savoir reel sur le framework cible (ex : "164.520(b)(1) prescribes plain language and organisation-specific content" -- jamais "HIPAA covers privacy").

#### Anti-pattern explicite (interdit)

| INTERDIT | RAISON | CORRECT |
|----------|--------|---------|
| `Has the controller implemented [verbatim]?` | Wrapper / paraphrase deguisee | Question d'audit sur un artefact verifiable |
| `evidence_expected: ["Documentation for X"]` | Placeholder generique | Liste >=2 artefacts concrets + owner + cadence |
| `rationale: "ISO covers this"` | Generique sans savoir | Citer numero controle ISO + ce qu'il prescrit + match/divergence |
| `confidence: 0.9` avec `source_type: inference` | Mensonge fiabilite | confidence in [0.5, 0.7] avec inference, ou trouver le crosswalk officiel |
| Question repete les memes 5 verbes du verbatim | Paraphrase mecanique | Reformuler autour de la verifiabilite |

#### GATE 2.4ter (bloquante)

Detection paraphrase + generic evidence + generic rationale :

```python
# Pseudo-code de la gate (implemente dans verify_evidence.sh Gate 12)
for q in questions:
 overlap = lemma_overlap(q['title'], q['requirement_text'])
 if overlap > 0.70:
 FAIL("paraphrase: title shares >70% lemmas with verbatim")
 for ev in q['preuves_attendues']:
 if re.search(r'documentation\s+(/|or|for)\s+evidence\s+for|evidence\s+for\s+requirement', ev, re.I):
 FAIL("generic evidence placeholder")
 for tgt, blk in q['cross_reference'].items():
 if tgt in REQUIRED_TARGETS and not blk.get('absence_justified'):
 rat = blk.get('rationale', '')
 if len(rat) < 60 or re.match(r'^(covers?|maps?|equivalent|partial|similar)\s+', rat, re.I):
 FAIL("generic rationale: no real knowledge of target framework")
```

FAIL = retour Phase 2.3bis/2.4ter pour re-author avec mobilisation Claude effective.

### 2.4bis cross_reference 5-targets par question (BLOQUANT, RIGUEUR PAR QUESTION)

User feedback 2026-05-26 : "la skill doit faire un travail exigeant". Cross_reference n'est PAS optionnel sur certaines questions, n'est PAS une projection facultative du mapping global -- c'est une obligation PAR question, sur les 5 cibles, avec source_type + confidence + source_url, comme dans le fichier mapping global.

Chaque question (TOUS frameworks) DOIT porter un champ `cross_reference` couvrant les 5 cibles obligatoires :

```json
"cross_reference": {
 "ISO_27001_2022": {
 "targets": ["A.5.34"],
 "source_type": "official_crosswalk",
 "source_url": "https://iso.org/standard/75652",
 "confidence": 0.9,
 "rationale": "Both controls require transparent privacy information to data subjects/PII principals."
 },
 "NIS2_DIRECTIVE": {
 "targets": ["Art21.2.j"],
 "source_type": "inference",
 "source_url": null,
 "confidence": 0.55,
 "rationale": "Indirect: NIS2 information security policies cover transparency only obliquely; no authoritative crosswalk published.",
 "thematic_domain": "Information security policies"
 },
 "HIPAA": {
 "targets": ["45 CFR 164.520"],
 "source_type": "official_crosswalk",
 "source_url": "https://csrc.nist.gov/pubs/ir/8374",
 "confidence": 0.95,
 "rationale": "NIST IR 8374 maps HIPAA Notice of Privacy Practices (164.520) to transparency obligations equivalent to GDPR Art 12-13."
 },
 "NIST_CSF_2_0": {
 "targets": ["GV.PO-01", "GV.OC-03"],
 "source_type": "authoritative_derived",
 "source_url": "https://csf.tools/reference/nist-cybersecurity-framework/v2-0/",
 "confidence": 0.8,
 "rationale": "GV.PO-01 (policy communicated) + GV.OC-03 (legal/regulatory requirements understood) cover the transparency obligation indirectly."
 },
 "ANSSI": {
 "absence_justified": "ANSSI 42 mesures (guide d'hygiene informatique) ne traite pas explicitement la transparence aux personnes concernees -- hors scope du guide. Pas de crosswalk officiel ANSSI vers GDPR Art 12-13."
 }
}
```

REGLES BLOQUANTES :
- Chaque question DOIT avoir un bloc `cross_reference` couvrant les 5 cibles (ISO_27001_2022, NIS2_DIRECTIVE, HIPAA, NIST_CSF_2_0, ANSSI).
- Pour chaque cible presente avec mapping, `source_type` + `confidence` + `rationale` OBLIGATOIRES. `source_url` obligatoire si `source_type` in {`official_crosswalk`, `authoritative_derived`}.
- Pour chaque cible absente, `absence_justified` OBLIGATOIRE avec raison factuelle (jamais "pas le temps de chercher").
- `targets[]` doit pointer sur des controles/articles existants dans le framework cible (pas inventes).
- Si `source_type == "inference"` : `thematic_domain` + `rationale` non-vide obligatoires, confidence dans [0.5, 0.7].
- Si `confidence > 0.7` : `source_type` dans {`official_crosswalk`, `authoritative_derived`} ET `source_url` non null.

Le fichier `config/mappings/{code}_unified_mappings.json` (Phase 3) reste la source agregee canonique ; chaque entree par question DOIT etre coherente avec celle du mapping global (memes targets, meme source_type, meme confidence).

### 2.4ter QUESTION QUALITY (BLOQUANT, RIGUEUR PAR QUESTION)

Chaque question (TOUS frameworks) DOIT porter les champs suivants, non-vides :

| Champ | Obligation | Validation |
|-------|-----------|-----------|
| `title` | Question interrogative (Does/Has/Are/Is/When/Where), passe AUDITOR VOICE STRICT v2 | regex Phase 2.3bis |
| `composite_obligation` | Label texte court qui resume l'obligation specifique evaluable par cette question | string non-vide |
| `source_paragraph` | Reference precise au paragraphe/sentence/sub-point du texte officiel (ex: "Art 13(2)(f) second clause") | string non-vide |
| `evidence_expected` | Liste >= 2 elements de preuve concrets qu'un auditeur peut demander | array len >= 2 |
| `cross_reference` | Bloc 5-targets (Phase 2.4bis) | voir 2.4bis |
| `control_reference` | Reference courte au controle/article source (ex: "Art 12(3)") | string non-vide |

GATE 2.4ter (bloquante): toute question manquant un de ces champs = FAIL retour Phase 2.

### 2.5 Conversion source YAML specifique

Extraction `ref_id` depuis URN : dernier segment apres le dernier `:`.
```
urn:framework:risk:req_node:{code}:1.1 -> "1.1"
```

Mapping des champs :
- `requirement_node.description` -> `question.title`
- `requirement_node.ref_id` -> `question.control_reference`
- `requirement_node.implementation_groups` -> `question.implementation_groups`
- `requirement_node.assessable: false` -> `section` (pas `question`)

### 2.6 ANTI-CLONE GATE (BLOQUANT pour `--clean-room`, RETEX 2026-05-26)

Avant Phase 4 (chargement DB), executer Jaccard similarity gate sur chaque
question vs (a) texte officiel source, (b) version legacy DB AGPL :

```python
def jaccard(a: str, b: str) -> float:
 sa, sb = set(a.lower().split()), set(b.lower().split())
 return len(sa & sb) / len(sa | sb) if sa | sb else 0.0
```

Seuils :

| sim vs officiel | sim vs legacy | Verdict | Action |
|-----------------|---------------|---------|--------|
| < 0.80 | < 0.80 | PASS | OK |
| 0.80-0.95 | * | WARN | Logger, garder |
| * | 0.80-0.95 | WARN_LEGACY | Logger, garder (toleré, pas contamination AGPL stricte) |
| >= 0.95 | * | FAIL_OFFICIAL | Re-rephrase obligatoire (forme operationnelle "Has...", "Does...") |
| * | >= 0.95 | FAIL_LEGACY | Re-rephrase obligatoire (contamination AGPL) |

Output : `data/anti_clone_report.json` avec verdict global + liste des FAILs +
warns. GATE : aucun FAIL toleré, le cycle reopen jusqu'a 0 FAIL.

Pattern de re-rephrase (RETEX NIST AI_RMF MAP 2.3 / MAP 3.4 / MANAGE 4.3) : quand
le texte officiel est court avec multi-noun lists, le Jaccard cape mecaniquement
au-dessus de 0.95. Fix = reformuler en question operationnelle :

- Original officiel : "Workforce diversity, equity, inclusion, and accessibility processes are prioritized..."
- FAIL clone (sim 0.96) : "Are workforce diversity, equity, inclusion, and accessibility processes prioritized..."
- PASS rephrase (sim 0.71) : "Has the team captured how a diverse range of perspectives shapes the way they conceive, build, and assess AI systems?"

Script : `recettes/anti_clone_gate.py` (template dans `references/anti-clone-gate.py`).

### 2.6bis COVERAGE GATE (BLOQUANT, RETEX 2026-05-26 W2A-W2E.1 incident)

Apres anti-clone Jaccard PASS, AVANT Phase 4 (load DB), executer le coverage
gate. C'est le gate qui ferme le trou des 8 frameworks W2A-W2E.1 importes avec
40-76% de couverture vs legacy.

```bash
bash .claude/skills/import-framework/scripts/coverage_gate.sh {CODE}
# OU avec justification explicite (raison precise obligatoire) :
bash .claude/skills/import-framework/scripts/coverage_gate.sh {CODE} \
 --justified "scope deliberement restreint aux obligations entite ; sub-acts deferred"
```

Verdicts :

| Ratio (new / max(legacy, ref)) | Verdict | Action |
|-------------------------------|---------|--------|
| `>= 0.90` | PASS | OK, continuer Phase 3 |
| `0.70 <= r < 0.90` sans `--justified` | WARN | exit 2 -- enrichir OU passer `--justified` |
| `0.70 <= r < 0.90` avec `--justified` | WARN_JUSTIFIED | OK, justification dans report |
| `< 0.70` sans `--justified` | FAIL | exit 1 BLOQUE -- re-authoring obligatoire |
| `< 0.70` avec `--justified` | PASS_JUSTIFIED | OK uniquement si justification factuelle (pas " legacy inflated") |

Le report `data/coverage_report.json` est COMMIT, lu par `verify_evidence.sh`,
et l'utilisateur peut auditer toute reduction de scope post-import.

Pattern de remediation FAIL (RETEX 2026-05-26) : appliquer Phase 2.4
STRONG_SPLIT a chaque article multi-sous-points. Une regulation type DORA
(Reg 2022/2554) avec 64 articles dont chacun a ~3-5 sous-paragraphes
(a)/(b)/(c) doit atteindre ~200-300 questions, pas 131. Si la regulation
porte 462 obligations dans le legacy, c'est qu'elle en a 462 -- les
splitter en sous-questions, pas les consolider.

---

## PHASE 3 -- MAPPINGS INTER-REFERENTIELS

### 3.1 Les 5 mappings obligatoires (sauf `--skip-mappings`)

User feedback recurrent : "les mappings doivent etre fiables, pas d'approximation". Cinq cibles obligatoires, chacune avec source autoritative tracable (`source_url` + `source_type`).

| Cible | Table source LIA-SEC | Crosswalk officiel autoritatif |
|-------|---------------------|--------------------------------|
| ISO 27001:2022 | `smsi_framework_mappings` | ISO/IEC 27001:2022 Annexe A + crosswalks ISO (ISO/IEC 27002:2022, ISO/IEC TS 27110) |
| NIS2 / ENISA 2024/2690 | `smsi_framework_mappings` | ENISA Implementing Regulation 2024/2690 (annexes mapping vers ISO 27002, NIS Cooperation Group reference document) |
| HIPAA | `smsi_framework_mappings` | NIST IR 8374 (HIPAA Security Rule Crosswalk to NIST CSF), HHS OCR HIPAA Security Rule Crosswalk |
| NIST CSF 2.0 | `smsi_framework_mappings` | NIST CSF 2.0 Informative References (CSF.tools / NIST official) -- subcategories `ID.AM-01` .. `RC.IM-02` |
| ANSSI Guides | `rule_anssi_mappings` (via tags regles) | ANSSI publications officielles : guide d'hygiene informatique 42 mesures, recommandations relatives a l'administration securisee, NIS2 transposition ANSSI |

### 3.1bis OFFICIAL CROSSWALK FIRST (BLOQUANT, anti-approximation)

Pour CHAQUE cible (ISO/NIS2/HIPAA/NIST_CSF/ANSSI), suivre l'ordre strict suivant. Ne JAMAIS sauter au niveau suivant sans avoir epuise le precedent.

| Niveau | Source | confidence | source_type | Action |
|--------|--------|-----------|-------------|--------|
| **1 -- OFFICIEL** | Publication autoritative (ISO, ENISA, NIST, HHS, ANSSI) | 0.95-1.0 | `official_crosswalk` | OBLIGATOIRE en premier. URL + sha256 + extrait verbatim commit sous `sources/crosswalks/{target}_official.{ext}` |
| **2 -- DERIVED** | Crosswalk derive d'une source autoritative (NIST CSF -> ISO via NIST Informative References, OWASP -> NIST via OWASP officiel) | 0.7-0.9 | `authoritative_derived` | Tracable a une source niveau 1 + transformation documentee dans `metadata.derivation` |
| **3 -- INFERENCE** | Rapprochement thematique (Phase 3.3 ANSSI domaines, similarite semantique source-cible) | 0.5-0.7 | `inference` | DERNIER RECOURS uniquement. Doit etre EXPLICITEMENT flagge + justification thematique citee |
| **ZERO -- ABSENT** | Aucune correspondance trouvee meme apres niveaux 1-3 | n/a | `none` | Documenter dans `metadata.{target}.absence_justified` : "no thematic overlap" / "out of scope" |

REGLE BLOQUANTE :
- Tout mapping `source_type=inference` SANS recherche documentee au niveau 1+2 = REJECTED.
- Tout mapping sans `source_url` (sauf inference dument flagge) = REJECTED.
- Tout mapping `confidence > 0.7` SANS `source_type` dans {`official_crosswalk`, `authoritative_derived`} = REJECTED (= mensonge sur la fiabilite).

#### Sources autoritatives connues (a verifier en premier)

| Pair (source -> target) | URL officielle a fetch |
|------------------------|----------------------|
| ISO 27001:2022 -> ISO 27002:2022 | iso.org/standard/75652 + annexe A mapping |
| NIS2 (Reg 2024/2690) -> ISO 27002 | eur-lex.europa.eu Annexes I-IV + ENISA reference document |
| HIPAA Security Rule -> NIST CSF 2.0 | NIST IR 8374 (csrc.nist.gov/pubs/ir/8374) |
| HIPAA Security Rule -> ISO 27001 | HHS OCR HIPAA Security Rule Crosswalk + NIST IR 8374 annexe |
| NIST CSF 2.0 -> ISO 27001 | NIST CSF 2.0 Informative References (csf.tools / nist.gov publications) |
| NIST CSF 2.0 -> NIS2 | ENISA NIS2 implementation guidance |
| ANSSI guide hygiene 42 mesures -> NIS2 | ssi.gouv.fr publications NIS2 transposition |
| ANSSI -> ISO 27001 | ssi.gouv.fr correspondances NIS / ISO publication |

WebSearch puis WebFetch des URL ci-dessus AVANT d'inferer. Si une URL est morte ou si la publication a evolue, mettre a jour la table inline.

### 3.2 Extraction des mappings depuis source YAML

Si des fichiers `mapping-{code}-and-*.yaml` existent dans la source :

```yaml
# Lire les requirement_mappings
# Convertir relationship + strength -> mapping_type + confidence
# intersect + 90 -> equivalent, 0.9
# intersect + 50 -> partial, 0.5
# subset -> partial, 0.7
# superset -> related, 0.6
# equivalent -> equivalent, 1.0
# related -> related, 0.5
```

Produire `config/mappings/{code}_unified_mappings.json` :

```json
{
 "metadata": {
 "source_framework": "{CODE}",
 "version": "{version}",
 "created_date": "{YYYY-MM-DD}",
 "source_file": "{nom fichier source YAML}"
 },
 "framework_mappings": [
 {
 "source_control": "{ref_id}",
 "target_frameworks": {
 "ISO_27001_2022": {
 "mappings": [{
 "target_control": "A.5.9",
 "type": "equivalent",
 "confidence": 0.95,
 "source_type": "official_crosswalk",
 "source_url": "https://iso.org/standard/75652",
 "source_sha256": "{sha256 du crosswalk commit}"
 }]
 },
 "NIS2_DIRECTIVE": {
 "mappings": [{
 "target_control": "Art21.2.a",
 "type": "partial",
 "confidence": 0.85,
 "source_type": "authoritative_derived",
 "source_url": "https://eur-lex.europa.eu/.../2024-2690",
 "derivation": "ENISA Reg 2024/2690 Annex I maps source to NIS2 Art21.2.a via control category X"
 }]
 },
 "HIPAA": {
 "mappings": [{
 "target_control": "164.308(a)(1)(ii)(A)",
 "type": "partial",
 "confidence": 0.9,
 "source_type": "official_crosswalk",
 "source_url": "https://csrc.nist.gov/pubs/ir/8374",
 "source_sha256": "{sha256 du IR 8374 commit}"
 }]
 },
 "NIST_CSF_2_0": {
 "mappings": [{
 "target_control": "ID.AM-01",
 "type": "equivalent",
 "confidence": 0.95,
 "source_type": "official_crosswalk",
 "source_url": "https://csf.tools/reference/nist-cybersecurity-framework/v2-0/",
 "source_sha256": "{sha256 du Informative References commit}"
 }]
 },
 "ANSSI": {
 "mappings": [{
 "target_control": "ANSSI_HYGIENE.R11",
 "type": "partial",
 "confidence": 0.65,
 "source_type": "inference",
 "thematic_domain": "Gestion des acces",
 "justification": "Le controle {ref_id} traite gestion identites/acces, mappe ANSSI_HYGIENE R11 (gestion comptes) par domaine thematique. Pas de crosswalk officiel ANSSI publie pour ce framework."
 }]
 }
 }
 }
 ]
}
```

### 3.2bis Keying robuste des mappings (resiste au split des sous-points)

Les mappings DOIVENT etre indexes sur le **numero d'article / prefixe de
controle**, PAS sur le `control_reference` complet de chaque question. Sinon le
split des sous-points (Phase 2.4) ou un enrichissement casse les correspondances :
les nouveaux sous-refs (`13.a`, `13.b`, ...) ne matchent plus une table indexee
sur le ref complet de l'ancienne question unique.

| Framework type | Cle de mapping | Extraction |
|----------------|---------------|-----------|
| Articles (CER, DORA, GDPR, directives) | numero d'article | regex `Art\.?\s*(\d+)` sur le `control_reference` |
| Controles a code (DEFSTAN, ISO, CIS) | prefixe de groupe (`23xx`, `A.8`) | tronquer le code au groupe thematique |

Chaque question -- y compris les sous-questions splittees -- resout sa cle, puis
recupere les memes cibles ISO/NIS2 que son parent. Resultat : N questions sous
un meme article partagent 1 entree de mapping logique (projetee en
`cross_reference` identique), et le compte de mappings reste stable quand le
questionnaire s'enrichit.

Incident 2026-05-24 (CER) : apres enrichissement 17 -> 30 questions, les mappings
sont tombes a 28 (les nouveaux sous-refs `13.a-f` etaient orphelins). Fix = keyer
sur le numero d'article (`Art\.?\s*(\d+)`) : les 6 sous-questions de l'Art 13
heritent toutes du mapping de l'article 13. Le compte est redevenu coherent.

GATE : `nb questions avec cross_reference non vide == nb total questions`. Une
question sans `cross_reference` = cle non resolue -> corriger le keying, pas la
question.

### 3.3 Inference des mappings ANSSI

Si pas de mapping ANSSI dans la source, inferer par domaine thematique :

| Domaine referentiel | Guides ANSSI correspondants |
|--------------------|-----------------------------|
| Gouvernance, politique SSI | ANSSI_HYGIENE (R1-R10) |
| Gestion des acces, IAM | ANSSI_HYGIENE (R11-R20), ANSSI_AD |
| Architecture reseau | ANSSI_HYGIENE (R21-R30), ANSSI_INTERCO |
| Chiffrement, TLS, SSH | ANSSI_TLS, ANSSI_SSH, ANSSI_CRYPTO |
| Journalisation, supervision | ANSSI_JOURNALISATION |
| Configuration systeme | ANSSI_LINUX |
| Administration SI | ANSSI_ADMIN |

Logger chaque inference dans `decision_log.jsonl` avec `confidence: "medium"`.

### 3.3bis VALIDATION DES MAPPINGS (BLOQUANT quand un crosswalk officiel n'existe pas)

Les mappings inter-referentiels sont une INFERENCE quand l'autorite ne publie pas
de crosswalk officiel. Avant de charger, VALIDER que chaque article cible existe et
correspond, sinon on charge des correspondances fausses (meme classe de risque que la
confabulation Phase 1b.0, mais sur les mappings au lieu des questions).

Procedure :
1. **Verifier les sujets des articles cibles** contre le TEXTE OFFICIEL du framework
 cible (ex: GDPR -> EUR-Lex Reg 2016/679 / gdpr-info.eu ; ISO -> norme). Confirmer
 que chaque `target_control` cite traite bien du sujet mappe (ne pas valider de
 memoire -- R18).
2. **Recouper avec une comparaison autoritative** si elle existe (cabinets, IAPP,
 DataGuidance, tables de transposition officielles). Ces sources servent a VALIDER
 le mapping, jamais a fournir le texte source des questions (qui vient du Phase 1b
 officiel).
3. **Documenter les divergences legales** dans `metadata.{target}_validation.divergences`
 du fichier `{code}_unified_mappings.json` : differences reelles entre les 2
 referentiels (base legale absente, delai different, regroupement 1->N, scope
 controller-only, etc.). Une divergence est un FAIT juridique, pas une erreur a
 corriger -- elle informe l'auditeur que la correspondance est approximative.
4. **Corriger les mappings faux** (mauvais article cible, one-to-many manque) AVANT
 chargement.

IMPORTANT -- separation des preoccupations :
- Les mappings n'alimentent PAS le questionnaire. Les questions viennent de
 `framework_surveys` (texte officiel du framework source). Un mapping faux ou une
 divergence ne casse jamais la creation/reponse du survey ; il degrade seulement la
 qualite du cross-reference. Ne jamais bloquer la creation du survey sur un mapping ;
 bloquer uniquement le CHARGEMENT de mappings non valides.

### 3.4 GATE utilisateur (5 cibles, fiabilite tracable)

Presenter un resume par cible avec ventilation `source_type` :

```
MAPPINGS GENERES (5 cibles obligatoires) :

 ISO 27001:2022 : N total
 - official_crosswalk : N (source: ISO Annexe A)
 - authoritative_derived : N
 - inference : N
 - absent : N (justified: ...)

 NIS2 / ENISA 2024/2690 : N total
 - official_crosswalk : N (source: ENISA Reg 2024/2690 Annexes)
 - authoritative_derived : N
 - inference : N
 - absent : N

 HIPAA : N total
 - official_crosswalk : N (source: NIST IR 8374 + HHS OCR Crosswalk)
 - authoritative_derived : N
 - inference : N
 - absent : N

 NIST CSF 2.0 : N total
 - official_crosswalk : N (source: NIST CSF 2.0 Informative References)
 - authoritative_derived : N
 - inference : N
 - absent : N

 ANSSI : N total
 - official_crosswalk : N (source: ssi.gouv.fr publications)
 - authoritative_derived : N
 - inference : N (par domaine thematique)
 - absent : N

VALIDATION : sujets d'articles cibles verifies vs texte officiel + recherche
 crosswalk officiel epuisee AVANT inference. Divergences : N.
FIABILITE : >= 80% non-inference par cible OU justification explicite par cible.
```

GATE 3.4 BLOQUANTE :
- Toute cible avec 100% inference + 0% recherche official_crosswalk documentee = REJECTED.
- Toute mapping confidence > 0.7 avec source_type != official_crosswalk/authoritative_derived = REJECTED.
- Toute cible avec >50% absence non-justifiee = REJECTED.

---

## PHASE 4 -- INTEGRATION POSTGRESQL

### 4.1 Creer la migration SQL (Pattern A R27, RETEX 2026-05-26)

Fichier : `cmd/sigma_web/migrations/0XX_{code}_handauthored.sql`

**R27 Pattern A (BLOQUANT) :** PAS de `BEGIN;` / `COMMIT;` top-level. Le runner
`psql -1 -v ON_ERROR_STOP=1 -f file.sql` wrappe deja le fichier dans une seule
transaction implicite. `scripts/psql_dry_run.sh` refuse les fichiers avec
BEGIN/COMMIT top-level. Le dry-run savepoint depend de l'absence de BEGIN/COMMIT.

**Dollar-quote dynamique :** pour eviter collision avec `$$` dans le contenu
JSONB (questions multi-ligne, regex), utiliser un tag dynamique `$mig0XX$`.

```sql
-- Migration 0XX: Import {CODE} hand-authored clean-room (RETEX YYYY-MM-DD)
-- Source: {source PDF/JSON URL} sha256={source_sha256}
-- License: {license_string}
-- Replaces: {legacy_code_if_any} (AGPL contamination cleared)
-- R27 compliant: no top-level BEGIN/COMMIT, dollar-quote tag $mig0XX$.

INSERT INTO compliance_frameworks (code, name, description, category, version, is_active, priority, metadata)
VALUES (
 '{CODE}',
 '{nom EN}',
 '{description EN}',
 'cybersecurity',
 '{version}',
 true,
 30,
 $mig0XX${
 "locale": "en",
 "source_authority": "{NIST|CISA|ANSSI|ENISA|...}",
 "license": "{US Government work (17 USC 105) = public domain | ...}",
 "source_url": "{URL officiel}",
 "source_sha256": "{sha256 du PDF/JSON commit sous sources/}",
 "provenance": "hand_authored_clean_room",
 "rephrase_author": "claude_inline",
 "agpl_contamination": "cleared",
 "legacy_replaces": "{LEGACY_CODE_if_any}",
 "imported_at": "{YYYY-MM-DD}",
 "implementation_groups": ["EI", "EE"]
 }$mig0XX$::jsonb
)
ON CONFLICT (code) DO UPDATE SET
 name = EXCLUDED.name,
 version = EXCLUDED.version,
 metadata = compliance_frameworks.metadata || EXCLUDED.metadata;

DO $mig0XX$
DECLARE expected_parts INT := {N};
DECLARE actual_parts INT;
BEGIN
 SELECT COUNT(*) INTO actual_parts FROM framework_surveys
 WHERE framework_id = (SELECT id FROM compliance_frameworks WHERE code = '{CODE}');
 IF actual_parts <> expected_parts THEN
 RAISE EXCEPTION 'Migration {CODE}: expected % parts, got %', expected_parts, actual_parts;
 END IF;
END $mig0XX$;
```

Dry-run avant apply :
```bash
scripts/psql_dry_run.sh cmd/sigma_web/migrations/0XX_{code}_handauthored.sql
# exit 0 = OK, exit 3 = SQL error, exit 1 = BEGIN/COMMIT top-level detected
```

Apply :
```bash
DBURL=$(systemctl cat lia-backend 2>/dev/null | awk -F'=' '/^Environment=DATABASE_URL/{print substr($0, index($0,"=")+1)}' | sed 's/^DATABASE_URL=//')
psql "$DBURL" -1 -v ON_ERROR_STOP=1 -f cmd/sigma_web/migrations/0XX_{code}_handauthored.sql
```

### 4.2 Charger les surveys en base

```sql
-- Pour chaque part_N.json :
INSERT INTO framework_surveys (framework_id, title, part_number, total_questions, questions, domains, is_active, version)
VALUES (
 (SELECT id FROM compliance_frameworks WHERE code = '{CODE}'),
 '{titre part}',
 {N},
 {nb_questions},
 '{questions_jsonb}'::jsonb,
 '{domains_jsonb}'::jsonb,
 true,
 '{version}'
)
ON CONFLICT (framework_id, part_number) DO UPDATE SET
 questions = EXCLUDED.questions,
 total_questions = EXCLUDED.total_questions;
```

### 4.3 Charger les mappings en base

```sql
-- Pour chaque mapping genere :
INSERT INTO smsi_framework_mappings (id, source_framework, source_control, target_framework, target_control, mapping_type, confidence, source_file)
VALUES (
 gen_random_uuid(),
 '{CODE}', '{source_ref}',
 '{TARGET}', '{target_ref}',
 '{type}', {confidence},
 '{source_file}'
)
ON CONFLICT (source_framework, source_control, target_framework, target_control) DO NOTHING;
```

---

## PHASE 5 -- INTEGRATION BACKEND GO

### 5.1 Modifier framework_loader.go

Ajouter dans `pkg/compliance/loader/framework_loader.go` :
- `getFrameworkFilename()` : case `"{CODE}": return "{CODE}"`
- `extractFrameworkID()` : case `"{code}": return "{CODE}"`
- `normalizeControlRef()` : pattern du ref_id
- `buildTagPattern()` : regex pour les tags YAML des regles

### 5.2 Modifier compliance_score_models.go (modele Go FrameworkDefinition)

Ajouter une entree dans `cmd/sigma_web/compliance_score_models.go` ->
`SupportedFrameworks` (slice `[]FrameworkDefinition`). La struct reelle (verifiee
2026-05-24, lignes 237-244) :

```go
type FrameworkDefinition struct {
 Code string `json:"code"`
 Name string `json:"name"`
 Version string `json:"version"`
 Description string `json:"description"`
 ControlMap map[string]string `json:"controlMap"` // control/objective ID -> ISO 27001 / NIS2 rapprochement
 Categories []string `json:"categories"`
}
```

Entree a ajouter (apres la derniere entree existante, ex: RECYF) :

```go
{
 Code: "{CODE}",
 Name: "{nom complet officiel}",
 Version: "{version}",
 Description: "{description courte}",
 ControlMap: map[string]string{
 // objectif/article -> rapprochement ISO 27001:2022 + NIS2 (inference, voir Phase 3)
 "{objectif_ou_article}": "ISO 27001 A.x.y / NIS2 Art21.2.z",
 },
 Categories: []string{ /* objectifs/domaines de niveau 1 */ },
},
```

Le `ControlMap` porte le MEME rapprochement ISO/NIS2 que les `cross_reference`
des questions (Phase 2.4bis) et le fichier mappings (Phase 3) -- coherence
obligatoire entre les 3.

**REGISTRATION SAFE (scan-scoring) -- pourquoi ca ne casse rien :** le
calculateur (`compliance_score_calculator.go:219`) ne fait contribuer un
framework au score global QUE si `fwScore.TestedControls > 0`. Un framework de
type QUESTIONNAIRE (Systeme A, pas de regle de scan qui matche ses controles) a
`TestedControls == 0` -> il est enregistre mais n'altere AUCUN score de scan
existant. La registration est donc sans risque pour le scoring (Systeme B).

> RAPPEL Systeme A vs B (`.claude/rules/compliance-frameworks-two-systems.md`) :
> un import = QUESTIONNAIRE DB (Systeme A), live des l'INSERT, ZERO build requis.
> L'ajout a `SupportedFrameworks` (Go, Systeme B) est OPTIONNEL -- a faire
> uniquement si on veut exposer le rapprochement Go OU preparer un futur scoring
> par scan. Il declenche alors `build_secure_lia.sh`. Ne PAS pretendre qu'un
> survey "ne marche pas sans build" : il marche des l'INSERT.

### 5.3 Ajouter au build

Verifier que les fichiers modifies sont dans `build_secure_lia.sh` (pas de nouveau fichier .go cree normalement).

---

## PHASE 5b -- CHARGEMENT EN BASE (OBLIGATOIRE)

Les fichiers JSON sur disque ne suffisent PAS. Il faut charger les donnees dans PostgreSQL.

### 5b.1 Charger les surveys dans framework_surveys

Pour chaque `part_N.json`, inserer dans `framework_surveys` avec le contenu JSONB :

```python
# Generer les INSERT SQL depuis les fichiers JSON
import json, glob
parts = sorted(glob.glob('config/survey/frameworks/{CODE}/*_part*.json'))
for i, path in enumerate(parts, 1):
 data = json.load(open(path))
 # INSERT INTO framework_surveys (framework_id, title, part_number, total_questions, questions, domains, is_active, version)
 # VALUES ((SELECT id FROM compliance_frameworks WHERE code = '{CODE}'), ...)
```

Verifier : `SELECT COUNT(*) FROM framework_surveys WHERE framework_id = (SELECT id FROM compliance_frameworks WHERE code = '{CODE}')` = N parts.

Mettre a jour `total_questions` dans `compliance_frameworks` :
```sql
UPDATE compliance_frameworks SET total_questions = (
 SELECT COALESCE(SUM(total_questions), 0) FROM framework_surveys
 WHERE framework_id = (SELECT id FROM compliance_frameworks WHERE code = '{CODE}')
) WHERE code = '{CODE}';
```

### 5b.2 Charger les mappings dans smsi_framework_mappings

Parser `config/mappings/{code}_unified_mappings.json` et inserer chaque mapping :

```sql
INSERT INTO smsi_framework_mappings (id, source_framework, source_control, target_framework, target_control, mapping_type, confidence, source_file)
VALUES (gen_random_uuid(), '{CODE}', '{ref}', '{TARGET}', '{target_ref}', '{type}', {conf}, '{file}')
ON CONFLICT (...) DO NOTHING;
```

Verifier : `SELECT COUNT(*) FROM smsi_framework_mappings WHERE source_framework = '{CODE}'` = N mappings.

### 5b.3 Tester la creation d'un assessment

Le framework doit etre utilisable dans le SMSI :
- Creer un assessment avec `framework_code = '{CODE}'`
- Verifier que `smsiSeedRequirementsFromFramework()` genere les `smsi_requirement_assessments`

---

## PHASE 6 -- VERIFICATION GATE (BLOQUANT)

Apres execution, AVANT de declarer termine :

- [ ] **SQL GATE** : Migration executee sans erreur (`psql -f migrations/0XX_*.sql`)
- [ ] **DATA GATE** : `SELECT * FROM compliance_frameworks WHERE code = '{CODE}'` retourne 1 ligne
- [ ] **SURVEY GATE** : `SELECT COUNT(*) FROM framework_surveys WHERE framework_id = (SELECT id FROM compliance_frameworks WHERE code = '{CODE}')` retourne N parts
- [ ] **MAPPING GATE** : `SELECT COUNT(*) FROM smsi_framework_mappings WHERE source_framework = '{CODE}'` retourne N mappings
- [ ] **BUILD GATE** : `bash cmd/sigma_web/build_secure_lia.sh` passe
- [ ] **SMOKE TEST** : `curl -s http://localhost:8081/api/compliance/frameworks | jq '.[] | select(.code=="{CODE}")'` retourne le framework

- [ ] **SURVEY DB GATE** : `SELECT SUM(total_questions) FROM framework_surveys WHERE framework_id = (SELECT id FROM compliance_frameworks WHERE code = '{CODE}')` retourne le bon nombre
- [ ] **MAPPING DB GATE** : `SELECT COUNT(*) FROM smsi_framework_mappings WHERE source_framework = '{CODE}'` retourne N mappings
- [ ] **UI GATE** : Le framework apparait dans la liste des frameworks disponibles

- [ ] **QUESTIONS ARRAY GATE** (anti-PT, incident 2026-05-23) : `framework_surveys.questions` DOIT etre un JSON ARRAY, pas un objet. Le endpoint calcule `total_controls = SUM(jsonb_array_length(questions))` ; un non-array = 0 = questionnaire NON repondable.
 ```sql
 SELECT part_number, jsonb_typeof(questions) qt, jsonb_array_length(questions) ql
 FROM framework_surveys WHERE framework_id=(SELECT id FROM compliance_frameworks WHERE code='{CODE}') ORDER BY part_number;
 ```
 CHAQUE ligne DOIT avoir `qt='array'` et `SUM(ql)` == nombre de questions. Une seule ligne `qt!='array'` -> STOP, corriger le load (questions = ARRAY plat concat de sections[].questions), recharger.
- [ ] **SOURCE EVIDENCE GATE** (preuve replay-verifiable, incident 2026-05-23) : POUR CHAQUE entree `sources[]` du manifest, le fichier source brut hashe DOIT etre commite dans `sources/` ET `sha256sum sources/<file>` DOIT redonner le `sha256` du manifest.
 ```bash
 # zero entree avec sha256 sans fichier commite correspondant
 for C in {CODE}; do
 nsrc=$(git ls-files "_alire/tracking/import-frameworks/$C/sources/" | grep -v 'manifest.json' | wc -l)
 [ "$nsrc" -eq 0 ] && echo "FAIL $C: manifest sha256 sans fichier source commite" || echo "OK $C: $nsrc source file(s)"
 done
 ```
 `FAIL` -> STOP : copier le fichier source depuis `_alire/temp/` vers `sources/`, verifier le sha256, committer. Si la page a derive : `SOURCE_NOTE.md` documentant les 2 sha (jamais de faux sha).

- [ ] **CONTROLE FORCE (BLOQUANT, non auto-declarable)** : lancer le verificateur. Les booleens sont CALCULES depuis la DB live + les fichiers commites (l'agent NE PEUT PAS les auto-affirmer). Il ecrit `sources/EVIDENCE.json` et flippe `evidence_verified=true` UNIQUEMENT si toutes les gates passent.
 ```bash
 bash .claude/skills/import-framework/scripts/verify_evidence.sh {CODE}
 # exit 0 + "PASS {CODE} ... evidence_verified=true" OBLIGATOIRE avant de declarer termine
 ```
 Exit != 0 ou `evidence_verified=false` -> l'import N'EST PAS termine : lire les `reasons`, corriger (questions array, source sha, tracking), re-lancer jusqu'a PASS. `EVIDENCE.json` est commite avec le framework (preuve machine-checkable, replay : `verify_evidence.sh --all`). Incident declencheur 2026-05-23 : l'utilisateur a re-insiste plusieurs fois sur les preuves apres PT (questions object) + DK/HR/RO (sha sans fichier) + PT (sha placeholder). Ce controle ferme les 3 classes de defaut.

- [ ] **CROSS_REFERENCE GATE** (Phase 2.4bis, keying Phase 3.2bis) : CHAQUE question
 porte un `cross_reference` non vide. Compte coherent malgre le split des sous-points.
 ```bash
 # nb questions sans cross_reference DOIT etre 0
 python3 - "$CODE" <<'PY'
 import json, glob, sys
 code = sys.argv[1]
 miss = 0; tot = 0
 for p in glob.glob(f'config/survey/frameworks/{code}/*_part*.json'):
 d = json.load(open(p))
 # On-disk format nests questions under sections[]; DB-loaded form is a flat array. Handle both.
 qs = list(d.get('questions', []) if isinstance(d.get('questions'), list) else [])
 for s in d.get('sections', []):
 qs += s.get('questions', [])
 for q in qs:
 tot += 1
 cr = q.get('cross_reference') or {}
 if not any(cr.get(k) for k in cr):
 miss += 1
 print(f'{code}: {tot} questions, {miss} sans cross_reference')
 sys.exit(1 if miss else 0)
 PY
 ```
 `miss > 0` -> cle de mapping non resolue (Phase 3.2bis) -> corriger le keying, pas la question.
- [ ] **MAPPING TARGET GATE** (anti-dangling, Phase 3.2bis) : chaque framework cible
 des mappings + des `cross_reference` inline DOIT se resoudre (via
 `framework_code_alias`) vers un code charge dans `compliance_frameworks`. Sinon le
 cross-reference pointe sur rien.
 ```bash
 python3 scripts/validate_framework_mappings.py --code {CODE}
 # exit 0 + "OK {CODE}: all target frameworks resolve to a loaded code" obligatoire
 ```
 `FAIL` -> ajouter l'alias manquant dans `config/mappings/framework_code_alias.json`
 (le canonique doit etre un code charge). Cette gate est aussi appliquee
 automatiquement par `verify_evidence.sh` (Gate 5 `mapping_targets_resolve`) qui la
 fait remonter dans `EVIDENCE.json` -- un target dangling fait passer
 `evidence_verified=false`.
- [ ] **MAPPING 5-TARGETS COVERAGE GATE** (Phase 3.1, BLOQUANT, anti-approximation) :
 les 5 cibles obligatoires (ISO_27001_2022, NIS2_DIRECTIVE, HIPAA, NIST_CSF_2_0, ANSSI)
 doivent CHACUNE etre presente dans `config/mappings/{code}_unified_mappings.json` avec
 >=1 entree OU une justification d'absence explicite dans `metadata.{target}.absence_justified`.
 ```bash
 python3 - "$CODE" <<'PY'
 import json, sys
 code = sys.argv[1].lower()
 m = json.load(open(f'config/mappings/{code}_unified_mappings.json'))
 required = {'ISO_27001_2022','NIS2_DIRECTIVE','HIPAA','NIST_CSF_2_0','ANSSI'}
 found = set()
 meta = m.get('metadata',{})
 for fm in m.get('framework_mappings',[]):
 for t in fm.get('target_frameworks',{}).keys():
 found.add(t)
 missing = required - found
 unjustified = [t for t in missing if not meta.get(t,{}).get('absence_justified')]
 if unjustified: print(f'FAIL missing 5-target mappings (no justification): {unjustified}'); sys.exit(1)
 if missing: print(f'WARN missing but justified: {missing}')
 print(f'OK 5-targets coverage: present={sorted(found & required)}, absent_justified={sorted(missing)}')
 PY
 ```
 `FAIL` -> ajouter mappings OU justification explicite par cible manquante.
- [ ] **MAPPING RELIABILITY GATE** (Phase 3.1bis, BLOQUANT, anti-approximation) : pour chaque
 mapping charge, `source_type` DOIT etre dans `{official_crosswalk, authoritative_derived, inference}`.
 Tout `confidence > 0.7` SANS `source_type` dans `{official_crosswalk, authoritative_derived}` = FAIL
 (= mensonge sur la fiabilite). Tout `source_type=inference` SANS `justification` = FAIL.
 ```bash
 python3 - "$CODE" <<'PY'
 import json, sys
 code = sys.argv[1].lower()
 m = json.load(open(f'config/mappings/{code}_unified_mappings.json'))
 bad_conf=[]; bad_src=[]; bad_inf=[]
 ALLOWED={'official_crosswalk','authoritative_derived','inference'}
 for fm in m.get('framework_mappings',[]):
 sc=fm.get('source_control')
 for tgt,blk in fm.get('target_frameworks',{}).items():
 for x in blk.get('mappings',[]):
 st=x.get('source_type'); cf=x.get('confidence',0)
 if st not in ALLOWED: bad_src.append((sc,tgt,st))
 if cf>0.7 and st not in {'official_crosswalk','authoritative_derived'}: bad_conf.append((sc,tgt,cf,st))
 if st=='inference' and not x.get('justification') and not x.get('thematic_domain'): bad_inf.append((sc,tgt))
 fail=False
 for label,arr in [('bad source_type',bad_src),('confidence>0.7 sans source autoritative',bad_conf),('inference sans justification',bad_inf)]:
 if arr: print(f'FAIL {label}: {arr[:5]}'); fail=True
 if fail: sys.exit(1)
 print('OK mapping reliability: all mappings carry valid source_type + traceable confidence')
 PY
 ```
 `FAIL` -> retour Phase 3.1bis : recherche crosswalk officiel pour les mappings `inference` avec confidence>0.7, OU baisser confidence a [0.5,0.7] + flag inference + justification thematique.
- [ ] **BENCHMARK GATE** (Phase 1.4) : `assessables_legacy` ET `assessables_reference`
 declares dans PLAN.md.
- [ ] **AUDITOR VOICE GATE** (Phase 2.3bis, BLOQUANT, STRICT v2) : 3 patterns d'echec
 bloquants (RETEX GDPR 2026-05-26 : 260/260 questions fake "Has ... implemented the
 following requirement -- '<dump verbatim>'" passaient regex naive). Toute question
 matchant un FAIL pattern = retour Phase 2.3bis re-authoring vraie voix audit.
 ```bash
 python3 - "$CODE" <<'PY'
 import json, glob, re, sys
 code = sys.argv[1]
 tot=0; w=[]; d_=[]; dump=[]
 # FAIL 1 -- wrapper "implemented the following requirement"
 wrapper_re = re.compile(r'(implemented|complied with|met|satisfied|addressed)\s+the\s+following\s+(requirement|control|obligation)', re.I)
 # FAIL 2 -- description normative
 desc_re = re.compile(r'^\s*(the\s+(organi[sz]ation|controller|processor|entity|supervisor|provider|operator|member\s+states)\s+shall|l\'?organisation\s+doit|personal\s+data\s+shall)', re.I)
 # FAIL 3 -- dump verbatim (title contient >= 80% des mots de requirement_text)
 def dump_ratio(t,r):
 if not r: return 0
 tw=set(x.lower() for x in re.findall(r'\w+',t))
 rw=set(x.lower() for x in re.findall(r'\w+',r))
 return (len(tw & rw)/len(rw)) if rw else 0
 for p in sorted(glob.glob(f'config/survey/frameworks/{code}/*_part*.json')):
 d=json.load(open(p))
 qs = d.get('questions', []) if isinstance(d.get('questions'), list) else []
 for s in d.get('sections', []): qs += s.get('questions', [])
 for q in qs:
 tot+=1
 t=(q.get('title') or '').strip()
 r=(q.get('requirement_text') or '').strip()
 if wrapper_re.search(t): w.append((q.get('id'),t[:80]))
 if desc_re.search(t): d_.append((q.get('id'),t[:80]))
 if r and dump_ratio(t,r)>=0.80: dump.append((q.get('id'),t[:80]))
 fails=len(w)+len(d_)+len(dump)
 print(f'{code}: {tot} questions')
 print(f' FAIL wrapper "implemented the following requirement": {len(w)}')
 print(f' FAIL description normative "The X shall ...": {len(d_)}')
 print(f' FAIL dump verbatim (title ~= requirement_text): {len(dump)}')
 for label,arr in [('wrapper',w),('desc',d_),('dump',dump)]:
 for x in arr[:3]: print(f' [{label}]', x[0], '::', x[1])
 sys.exit(1 if fails else 0)
 PY
 ```
 `bad > 0` -> retour Phase 2.3bis : reformuler en voix d'auditeur.
- [ ] **COMPOSITE DECOMPOSITION GATE** (Phase 2.3bis, BLOQUANT) : pour CHAQUE item
 framework avec >=2 obligations distinctes verifiables, le compte de questions >= 2,
 ET justification dans `data/composite_audit.json` :
 ```bash
 test -f _alire/tracking/import-frameworks/$CODE/data/composite_audit.json || { echo "FAIL composite_audit.json absent"; exit 1; }
 python3 -c "
 import json,sys
 d=json.load(open('_alire/tracking/import-frameworks/$CODE/data/composite_audit.json'))
 bad=[e for e in d if e.get('n_obligations',0)>=2 and e.get('n_questions',0)<2]
 ceil=[e for e in d if e.get('n_questions',0)>3 and not e.get('justification')]
 if bad: print('FAIL composite missing splits:', bad[:5]); sys.exit(1)
 if ceil: print('FAIL composite over plafond sans justification:', ceil[:5]); sys.exit(1)
 print('OK', len(d), 'items audited')
 "
 ```
 FAIL -> retour Phase 2.3bis : splitter les items COMPOSITE non-splittes OU justifier le depassement du plafond.
- [ ] **COVERAGE GATE** (Phase 2.6bis, BLOQUANT, RETEX W2A-W2E.1) :
 ```bash
 bash .claude/skills/import-framework/scripts/coverage_gate.sh {CODE}
 # Exit 0 = PASS (ratio >= 0.9) ou PASS_JUSTIFIED ou WARN_JUSTIFIED
 # Exit 1 = FAIL (re-author with STRONG_SPLIT obligatoire)
 # Exit 2 = WARN sans justification (enrichir ou --justified "<raison>")
 ```
 `data/coverage_report.json` DOIT etre commit. Re-fait Phase 2.4 STRONG_SPLIT
 si FAIL : chaque sous-point (a)/(b)/(c)/(i)/(ii)/(iii) -> 1 sous-question
 evaluable, JAMAIS consolider. Si reduction acceptable de scope, passer
 `--justified "<raison precise factuelle>"`.
- [ ] **GO ENTRY GATE** (si Phase 5.2 faite) : l'entree `SupportedFrameworks` a un
 `ControlMap` coherent avec les `cross_reference` ; build passe ; le framework
 questionnaire n'altere aucun score de scan (`TestedControls == 0`, contribution nulle).

Si une gate echoue : STOP, corriger, re-gate.

---

## PHASE 6bis -- COMPLETION GATE (BLOQUANTE, NON-CONTOURNABLE)

INTERDIT de declarer le skill termine si l'une de ces conditions n'est pas vraie :

1. `bash .claude/skills/import-framework/scripts/verify_evidence.sh {CODE}` exit code 0
2. `_alire/tracking/import-frameworks/{CODE}/sources/EVIDENCE.json` existe ET contient `"evidence_verified": true`
3. `EVIDENCE.json` est COMMIT (pas juste sur disque) -- `git ls-files _alire/tracking/import-frameworks/{CODE}/sources/EVIDENCE.json` retourne le path
4. Toutes les gates Phase 6 cochees avec commande de verification executee (pas declaratif "OK")
5. Scoring agentique /50 calcule ET affiche dans le Completion Report (jamais omis)

Verification automatique :

```bash
CODE={CODE}
bash .claude/skills/import-framework/scripts/verify_evidence.sh "$CODE" || { echo "FAIL verify_evidence -- skill NON terminee"; exit 1; }
test -f "_alire/tracking/import-frameworks/$CODE/sources/EVIDENCE.json" || { echo "FAIL EVIDENCE.json absent"; exit 1; }
python3 -c "import json,sys; d=json.load(open('_alire/tracking/import-frameworks/$CODE/sources/EVIDENCE.json')); sys.exit(0 if d.get('evidence_verified') is True else 1)" || { echo "FAIL evidence_verified != true"; exit 1; }
git ls-files "_alire/tracking/import-frameworks/$CODE/sources/EVIDENCE.json" | grep -q . || { echo "FAIL EVIDENCE.json pas commit"; exit 1; }
echo "PASS Completion Gate -- skill peut declarer termine"
```

Si une condition manque -> skill NON terminee. Lire les `reasons` de EVIDENCE.json. Corriger. Re-run verify_evidence.sh. Boucler jusqu'a PASS. Si bloque apres 3 cycles REPLAN -> escalade utilisateur (jamais abandonner silencieusement).

INTERDIT (deja constate sur des imports precedents) :
- Dire "import termine" alors que questionnaire jamais charge en DB
- Dire "mappings OK" alors que `smsi_framework_mappings` vide pour {CODE}
- Dire "tracking commit" alors que EVIDENCE.json absent ou `evidence_verified=false`
- Dire "OK avec petites limitations" sans lister precisement les limitations dans Completion Report
- Skipper Phase 6bis et passer directement Phase 7

---

## PHASE 7 -- LIVRAISON

### 7.1 Completion Report (format OBLIGATOIRE, verdict explicite)

Produire `_alire/temp/IMPORT_{CODE}_{YYYY-MM-DD}.md` ET afficher dans la conversation :

```
Completion Report

Skill: /import-framework
Framework: {CODE}
Status: ACHIEVED | PARTIALLY_ACHIEVED | FAILED

Sub-tasks:
1. source detection + inventaire : {result}
2. proof-of-research + texte officiel : {result}
3. conversion YAML/PDF -> JSON parts : {result} (N parts, M questions)
4. mappings ISO/NIS2/ANSSI : {result} (N mappings)
5. migration SQL + load DB : {result}
6. verification gate (verify_evidence) : PASS | FAIL
7. livraison + scoring : {result}

Evidence (Phase 6bis obligatoire):
- EVIDENCE.json commit: {git_hash} | ABSENT
- evidence_verified: true | false
- verify_evidence.sh exit: 0 | N

Scoring agentique:
- Decomposition: /10
- Planification: /10
- Replanification: /10
- Outillage: /10
- Tracabilite: /10
- Total: /50 -- {Exemplaire >=40 | Acceptable 30-39 | RETEX obligatoire <30}

Inventaire livre:
| Element | Valeur |
|---------|--------|
| Code | {CODE} |
| Nom | {nom officiel} |
| Version | {version} |
| Source | {chemin/URL} |
| Format source | YAML structuree / PDF / custom |
| Locale | en |
| Exigences evaluables | N |
| Domaines | N |
| Parts survey | N |
| Mappings ISO 27001 | N (N equivalent, N partial) |
| Mappings NIS2/ENISA | N (N equivalent, N partial) |
| Mappings ANSSI | N (N inferences) |
| Migration SQL | cmd/sigma_web/migrations/0XX_{code}.sql |
| Fichiers Go modifies | framework_loader.go, compliance_score_models.go (si Phase 5.2) |

Open items (OBLIGATOIRE si Status != ACHIEVED):
- {liste precise, jamais "petites limitations" / "quelques details" / "presque OK"}

Next steps:
- {actions concretes, owner, ETA}
```

Si Status != ACHIEVED -> RETEX obligatoire :
`_alire/02_LOGS/Journals/retex/RETEX_IMPORT_FW_{CODE}_{YYYY-MM-DD}.md` avec root cause + replans tentes + alternatives non explorees.

### 7.2 Mettre a jour le plan persistant

Status -> TERMINE, cocher toutes les etapes, ajouter le resultat.

---

## REVISION D'UN FRAMEWORK DEJA EN DB (sous-mode)

Quand un framework EXISTE deja dans `framework_surveys` mais ses titres sont casses
(node_id prefixes, sous-points orphelins, fragments) -- cas du bulk-load mars 2026
qui a charge 305 frameworks dont 59 flagged >=20% titres defectueux.

**Outils prets a l'emploi** (dans `_alire/tracking/framework-questionnaire-audit/`,
testes 2026-05-25 sur 39 frameworks reels) :

| Script | Role |
|--------|------|
| `framework_reimport.py <src.yaml> <CODE> <out>` | Re-import propre : fold colon-stems + lowercase children en phrase complete verbatim, strip [nodeN], context parent restaure |
| `recettes/audit_titles.py <dir>` | Recette bloquante : exit 1 si >0 titre defectueux (node_id/continuation/subpoint/dangling/bullet/tiny) |
| `load_revised.py <CODE> <dir> [sql]` | Genere SQL `DELETE+INSERT framework_surveys` (title<=255, numerotation sequentielle enumerate) |
| ~~`enrich_revised.py`~~ | **BANNED 2026-05-26** -- archive sous `_archive_banned_scripts/`. Generait `Has your organization implemented the following requirement -- "{dump verbatim normatif}"` (wrapper fake, FAIL Phase 2.3bis STRICT v2). User feedback : "cest honteux ce job si jutilise chatgpt je 'ai de vrais quesiton". REMPLACEMENT : Claude inline hand-author par question, batche par article. |
| `extract_official_mappings.py [--apply]` | Pull 46 fichiers `mapping-*.yaml` (legacy library), parse `requirement_mapping_set` ET `requirement_mapping_sets` (liste), resout via `config/mappings/framework_code_alias.json`, charge ON CONFLICT DO NOTHING |
| `in_place_clean.py <CODE> [--apply]` | Strip [nodeN] cote DB live (frameworks sans source standalone) |
| `generate_tracking.py <CODE> [--batch]` | Auto-genere PLAN/PROOF/INVENTORY/ARTICLES_VERBATIM + manifest sha256 depuis source. Necessaire pour passer verify_evidence.sh |

**Workflow standard de revision** (par framework) :

```
# 1. Identifier la source dans la lib legacy + VERIFIER le nom DB avant action
curl -sSL https://raw.githubusercontent.com/intuitem/ciso-assistant-community/main/backend/library/libraries/<file>.yaml -o /tmp/<CODE>.yaml
python3 -c "import yaml;d=yaml.safe_load(open('/tmp/<CODE>.yaml'));print(d['objects']['framework']['name'])"

# 2. Re-import propre + recette (exit=0 obligatoire)
python3 _alire/tracking/framework-questionnaire-audit/tooling/framework_reimport.py /tmp/<CODE>.yaml <CODE> /tmp/<CODE>_out
python3 _alire/tracking/framework-questionnaire-audit/recettes/audit_titles.py /tmp/<CODE>_out

# 3. Remplacer repo + load DB
rm -rf config/survey/frameworks/<CODE> && mkdir -p config/survey/frameworks/<CODE>
cp /tmp/<CODE>_out/*.json config/survey/frameworks/<CODE>/
cp /tmp/<CODE>.yaml _alire/tracking/framework-questionnaire-audit/sources/<CODE>_source.yaml
python3 _alire/tracking/framework-questionnaire-audit/tooling/load_revised.py <CODE> /tmp/<CODE>_out /tmp/<CODE>_out/load.sql
psql "$DBURL" -v ON_ERROR_STOP=1 -f /tmp/<CODE>_out/load.sql
psql "$DBURL" -tAc "UPDATE compliance_frameworks SET total_questions=(SELECT COALESCE(SUM(jsonb_array_length(questions)),0) FROM framework_surveys fs WHERE fs.framework_id=compliance_frameworks.id), is_active=true WHERE code='<CODE>'"

# 4. Hand-author voix d'auditeur + COMPOSITE DECOMPOSITION (Claude inline, Phase 2.3bis)
# INTERDIT enrich_revised.py (BANNED 2026-05-26 -- wrapper fake "Has ... implemented the following requirement -- '{dump}'").
# OBLIGATOIRE Claude lit chaque article du fichier source, decompose en obligations distinctes,
# et ecrit 1 question auditeur par obligation (Does/Has/Are ... ?). Pas de script Python batch.
# Cross-reference inline = patch manuel dans le JSON apres rephrase (depuis smsi_framework_mappings).

# 5. Generer tracking + verify_evidence (BLOQUANT)
python3 _alire/tracking/framework-questionnaire-audit/tooling/generate_tracking.py <CODE>
bash .claude/skills/import-framework/scripts/verify_evidence.sh <CODE>
# exit 0 obligatoire
```

**LEÇONS APPRISES 2026-05-25 (a NE PAS rejouer)**

| Anti-pattern | Symptome | Mitigation |
|--------------|----------|------------|
| Loader glob `*_part*.json` trop large | Code contenant "PART" (EASA_PART_IS_D_OR) attrape master_config -> KeyError "domain_info" | Glob `*_part[0-9]*.json` (chiffre obligatoire) |
| Title NOT truncated dans loader | varchar(255) overflow noms de domaine longs -> INSERT FAIL silencieux, framework charge a moitie | `di['name'][:250]` |
| Parse `part_number` du nom de fichier | Collision sur frameworks numerotes part 10 deux fois (ESSENTIAL_EIGHT) -> UNIQUE constraint violation | `enumerate(parts,1)` sequentiel |
| Resolveur xref naif (string equality) | 0 match GDPR alors que 761 mappings existent (formats `Art 13` vs `13.x` vs `Art.35`) | Normalisation article-numero `norm_keys()` + bidirectionnel (source+target) |
| Parser mapping YAML monoforme | 0 rows sur fichiers `-and-` (utilisent `requirement_mapping_sets` LISTE pluriel) | Lire `requirement_mapping_set` singulier ET `requirement_mapping_sets[]` |
| Tracking par framework absent | `verify_evidence FAIL "missing tracking"` sur tout framework revise | `generate_tracking.py` auto-derive PLAN/PROOF/INVENTORY/VERBATIM depuis source committee + manifest sha256 |
| `is_active=false` silent post-load | Framework invisible UX sans erreur | UPDATE explicite `is_active=true` post-load |
| Inflation sub-questions par agent | Sonnet sans gate strict produit 3 sub-q/exigence = x4 (DORA 208->970) = inutilisable | Brief STRICT : default=0 sub_q, max 3, "COMPOSITE only" criteres explicites (2+ obligations distinctes verifiables, lists multiple subjects, mixes process+evidence+responsibility) |
| Hardcoded `weight=6` partout | Pas de signal scoring, pas de priorisation | Phase scoring SEPAREE : agent sonnet calibre weight 1-10 par exigence (criticite + sanction + scope) + justification basee texte |

## ANTI-PATTERNS

| INTERDIT | CORRECT |
|----------|---------|
| Generer le contenu UI/questions en francais | Locale EN par defaut (R8), titres et options en anglais |
| Pretendre qu'un survey "ne marche pas sans build Go" | Systeme A : live des l'INSERT, ZERO build (Phase 5.2 Go = optionnel) |
| 1 question = 1 article haut-niveau (import mince) | Benchmark granularite (Phase 1.4) + split sous-points (Phase 2.4) |
| Copie verbatim du texte normatif comme question ("The organisation shall...") | Phase 2.3bis VOIX D'AUDITEUR : reformuler interrogatif ("Has the organisation...?") |
| Wrapper fake "Has your organization implemented the following requirement -- '{dump verbatim}'" (pattern enrich_revised.py BANNED) | Claude inline hand-author par question, decompose COMPOSITE, evidence_expected concret. PAS de script Python batch de rephrase. |
| 1 item framework -> 1 question quand l'item porte >=2 obligations distinctes | Phase 2.3bis COMPOSITE DECOMPOSITION : 1 question par obligation verifiable, justification dans composite_audit.json |
| Inflation x3 par defaut (sonnet sans gate strict) | Phase 2.3bis garde-fous : default sub_q=0, max 3, justification COMPOSITE obligatoire |
| Keyer les mappings sur le ref complet de la question | Keyer sur numero d'article / prefixe de groupe (Phase 3.2bis) |
| Pretendre que cross_reference/mappings sont "officiels" | Labelliser INFERRED, confidence 0.6-0.7 (Phase 2.4bis) |
| Ignorer les mappings ISO/ANSSI/NIS2 | Les 3 mappings sont OBLIGATOIRES sauf `--skip-mappings` |
| Hardcoder le mot de passe PostgreSQL | `$LIA_DB_PASS` / `psql_lia()` |
| Creer un fichier Go sans l'ajouter au build | Modifier les fichiers existants, pas en creer de nouveaux |
| Sauter la GATE verification | Toutes les gates doivent etre vertes |
| Inventer des mappings sans source | Logger `confidence: "low"` et signaler a l'utilisateur |
| Continuer apres 2 echecs consecutifs | Invoquer `/replan` |
| Rephrase clean-room via API LLM externe (Grok/OpenAI/Mistral) | Claude inline dans la conversation (RETEX 2026-05-26 NIST Tier 1) -- exception si l'utilisateur cite explicitement le provider |
| Migration SQL avec `BEGIN;` / `COMMIT;` top-level | Pattern A R27 : pas de transaction control top-level, dollar-quote dynamique `$mig0XX$` (Phase 4.1) |
| Commit `git add` puis `git commit` direct sur tree partagee | `safe_commit.sh -C . -m "msg" -- file1 file2 ...` (R28 shared-tree-race-safe-commit) |
| Skip anti-clone Jaccard gate en mode `--clean-room` | GATE 2.6 BLOQUANTE : 0 FAIL toleré vs official ET vs legacy DB |
| Omettre `provenance` / `source_sha256` / `agpl_contamination` dans metadata | Phase 4.1 : tous les champs provenance OBLIGATOIRES pour clean-room |
| Consolider plusieurs sous-points (a)/(b)/(c) en 1 umbrella question | Phase 2.4 STRONG_SPLIT : 1 sous-question hand-authored par sous-point normatif. Le clean-room est un changement de TEXTE, pas de SCOPE. |
| Reduire le nombre de questions vs legacy en pretextant " legacy inflated" | Phase 2.6bis Coverage gate BLOQUE si new < legacy * 0.9 sans `--justified`. " legacy inflated" REFUSEE comme justification -- c'est la granularite que Phase 2.4 impose. |
| Skip coverage_gate.sh ou omettre `assessables_legacy` dans PLAN.md | Phase 1.4 + Phase 2.6bis : baselines obligatoires dans PLAN.md, coverage_gate.sh exit 0 obligatoire, `data/coverage_report.json` commit. |

## Dependencies

- Required tools : Read, Write, Edit, Bash, Grep, Glob, Agent
- Required skills : `/replan` (si echecs), `/analyze-repo` (si source GitHub)
- Required scripts : `scripts/psql_dry_run.sh` (Phase 4.1 dry-run), `.claude/skills/liaprobe-fingerprint-rebuild/scripts/safe_commit.sh` (R28 commit final)
- Retry policy : Si un outil echoue, retry 1 fois. Si echec, reporter et STOP.

## Sources supportees

| Source | Exemples | Methode |
|--------|----------|---------|
| YAML structuree | `{code}.yaml`, `dora.yaml` | Parsing direct |
| source YAML mapping YAML | `mapping-{code}-and-iso27001-2022.yaml` | Extraction URN |
| Repo GitHub | Tout repo contenant des YAML structurees avec URN | Clone + extraction |
| PDF officiel | Publication ANSSI, ENISA, ISO | OCR + extraction |
| JSON/CSV custom | Tableau de controles | Mapping colonnes |
