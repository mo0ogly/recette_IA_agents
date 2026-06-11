---
name: fingerprint-lab-improve
description: >
  Fingerprint Lab Improve v5.0 -- Boucle autonome OBJECTIVE->RESEARCH->ACT->OBSERVE->EVALUATE->LOOP or COMPLETE.
  Amelioration systematique des patterns de detection LiaProbe. 8 sources open-source (LOCAL first),
  recette offline 5406 cas, quality gates bloquants, REPLAN sur chaque FAILURE avec 2+ alternatives,
  RETEX affiche obligatoire. Composes with /konrad-kurze (meta-cognitive auditor invoked before the
  3rd REPLAN on the same step). Triggers sur fingerprint, detection lab, ameliorer la detection,
  FP sur le port, score lab, pourquoi ca matche pas, qualification IP, recette, LiaProbe fingerprint patterns.
---

# fingerprint-lab-improve v5.0 -- Boucle Autonome

## Commands

| Command | Action |
|---------|--------|
| `fix <TAXONOMY>` | Fix a pattern. Boucle autonome complete avec gates. |
| `batch <PORTS>` | Fix multiple ports. Vagues paralleles (max 5). |
| `scan` | Full lab ou live IP scan. Compare expected vs detected. |
| `recette` | Offline recette : `liaprobe --mode recette -f liaprobe/recette/datascan_recette.jsonl` (5406 cas, ~30s). |
| `score` | Score actuel vs cible (recette + lab + IPs). |
| `retex` | RETEX + rules + skill update. |
| `rules` | Show RETEX rules (`references/retex-rules.md`). |
| `add <TECHNO>` | Add technology to lab + pattern + test. |
| `convert` | Batch conversion : `scripts/tools/convert_*_to_lia.py`. |

## Model Selection (MANDATORY)

| Phase | Model | Rationale |
|-------|-------|-----------|
| RESEARCH (capture, grep repos) | `haiku` | File reads, curl/nc = no reasoning |
| EVALUATE (diagnostic pattern) | `sonnet` | Deep pattern analysis + engine understanding |
| ACT (pattern/engine fix) | `sonnet` | Code writing requires reasoning |
| OBSERVE (recette, gates) | `haiku` | Run scripts, check scores, write RETEX |

JAMAIS RESEARCH/OBSERVE sur sonnet. JAMAIS EVALUATE/ACT sur haiku.

---

## Boucle autonome (MANDATORY -- FORBIDDEN to skip a phase)

```
OBJECTIVE -> DECOMPOSE -> RESEARCH -> EVALUATE -> ACT -> OBSERVE -> REPLAN? -> LOOP or COMPLETE
                                           ^___________________________|
                                           LOOP si FAILURE
```

Pour `batch`: RESEARCH en parallele (max 5 ports). EVALUATE/ACT/OBSERVE sequentiel par port.

---

### OBJECTIVE -- Decomposition ecrite obligatoire

Avant toute action :

```
## Decomposition
Objective: {fix TAXONOMY / improve detection rate}
Sub-tasks:
1. [TRIVIAL] Capture real response -- role: RESEARCH
2. [MODERATE] Read 3+ open-source sources -- role: RESEARCH
3. [COMPLEX] Diagnose why pattern fails -- role: EVALUATE
4. [COMPLEX] Fix pattern or engine -- role: ACT
5. [TRIVIAL] Rebuild + scan + recette -- role: OBSERVE
```

**INTERDIT de lancer des agents sans decomposition ecrite.**

---

### RESEARCH -- Capture + exploration sources (BLOCKING GATE)

#### Step 0 : Cleanup recurring FP
```bash
.claude/skills/fingerprint-lab-improve/scripts/cleanup_fp.sh
```
**GATE PRE-SCAN**: scan port 18080. Si FP -> STOP, disable, re-scan.

#### Step 1 : Capture real response
```bash
curl -sI http://localhost:PORT/
curl -sL http://localhost:PORT/ | head -50
echo "" | timeout 3 nc -w2 127.0.0.1 PORT | head -5
```

#### Step 2 : GATE EXPLORATION (BLOCKING -- 3+ sources obligatoires)

**INTERDIT de fixer sans lire les sources.** Detail : `references/code-exploration.md`.

9 sources, dans l'ordre :
1. **Onyphe local (PRIORITAIRE, LOCAL)**: `python3 scripts/onyphe_rule_evidence.py --tier <TIER> --rule <TAXO>` -> mine les catalogues Onyphe (cpe_list 6019 CPE, products_versions 3367, http_components, onyphe_app_groundtruth.jsonl per-host, onyphe_recette_16641.jsonl). ECRIT l'evidence + sha + journal DANS `patterns/<tier>/captures/<TAXO>/onyphe/`. Lire le `evidence.jsonl` produit.
2. **Local repos (Nuclei)**: `find data/fingerprints/repositories/nuclei-templates -iname "*TECHNO*" -name "*.yaml"` -> READ
3. **Local repos (Wappalyzer)**: `grep -rl "TECHNO" data/fingerprints/repositories/wappalyzer/src/technologies/` -> READ
4. **Local repos (Recog)**: `grep -rl "TECHNO" data/fingerprints/repositories/recog/xml/` -> READ
5. **Converter existant**: `ls scripts/tools/convert_*_to_lia.py` -> USE si applicable (R30)
6. **Websearch**: Shodan/Censys pour banners production reelles
7. **Pattern LIA actuel**: `data/fingerprints/lia/TAXONOMY.json` -> READ
8. **Si FP**: lire patterns FP (Section C code-exploration.md)
9. **Si engine blocker**: lire `executor.go`, `matcher.go`, `probe.go`, `loader.go`

Evaluation : SUCCESS (3+ sources lues, dont Onyphe source 1 OBLIGATOIRE) | FAILURE (0 sources) -> STOP, lire d'abord.

**R35 Onyphe evidence per-rule (BLOQUANT).** Toute rule creee ou modifiee
DOIT, avant fin de phase OBSERVE, avoir son evidence Onyphe attachee via
`scripts/onyphe_rule_evidence.py` : ecrit `patterns/<tier>/captures/<TAXO>/onyphe/{evidence.jsonl,provenance.json}`
(sha256 par source Onyphe + sha de l'evidence, replayable) ET une entree
append-only dans `_alire/tracking/liaprobe-fingerprint-rebuild/sessions/<date>_onyphe-evidence/journal.jsonl`.
`evidence_count=0` n'est PAS un echec (preuve qu'on a cherche : la techno
peut etre absente de cette tranche Onyphe) mais le repertoire + provenance
+ journal restent obligatoires. Loader-safe : `loader.go:99` skip IsDir +
non-recursif, `captures/` jamais traverse. Reference :
feedback_evidence_tracking_mandatory.

---

### EVALUATE -- Diagnostic

4 questions AVANT tout fix :
1. Pourquoi le pattern correct ne matche pas ?
2. Pourquoi les FP matchent ?
3. Quel signal SPECIFIQUE differencie cette technologie ?
4. **Est-ce un bug moteur affectant d'autres patterns ? (R29)** Si OUI -> fix moteur d'abord.

Evaluation apres diagnostic :
```
## Observation -- Diagnostic
Result: {root cause identifiee}
Expected: {pattern devrait matcher}
Status: SUCCESS (cause trouvee) | PARTIAL (hypothese) | FAILURE (inconnu)
```

FAILURE sur diagnostic -> REPLAN avec approche alternative (capture differente, autre source).

---

### ACT -- Fix pattern ou moteur

**R29 PRIORITE ABSOLUE : fix moteur 1:N > fix pattern 1:1.**
Toujours demander : "ce bug affecte-t-il d'autres patterns ?"

**R25 BLOQUANT avant fix moteur :**
Avant de modifier `matcher.go`, `executor.go`, `probe.go`, `loader.go` :
- Lire comment les repos locaux gerent le meme probleme (2+ repos obligatoires)
- Un fix moteur impacte 12000+ patterns -- chaque decision doit etre informee

**R30 INTERDIT de creer 10+ patterns manuellement si un converter existe :**
```bash
scripts/tools/convert_recog_to_lia.py      # 4662 Recog XML -> JSON
scripts/tools/convert_nuclei_to_lia.py     # Nuclei YAML -> JSON
scripts/tools/convert_wappalyzer_to_lia.py # Wappalyzer -> JSON
scripts/tools/convert_nmap_probes_to_lia.py # Nmap probes -> JSON
```

Apres fix pattern ou moteur :
```bash
# Disable FP + verify (R13)
.claude/skills/fingerprint-lab-improve/scripts/cleanup_fp.sh

# Sync 3 copies (R23 : inclure subdirs by-taxonomy/)
.claude/skills/fingerprint-lab-improve/scripts/sync_fingerprints.sh --all

# Build
cd /opt/lia-sec/dev/liaprobe && make build 2>&1 | tail -1

# Scan cible
cd /opt/lia-sec/dev && timeout 30 ./liaprobe/bin/liaprobe --mode specific --ports PORT 127.0.0.1 2>/dev/null
```

---

### OBSERVE -- Gates qualite (BLOCKING)

**GATE QUALITY (4/4 requis) :**
```
[ ] Technologie correcte = confidence la plus haute
[ ] Confidence >= 0.90
[ ] Version extraite (si exposee)
[ ] 0 FP (hors Apache/PHP sous-jacent)
```
Failure sur gate -> retour EVALUATE, pas un simple retry.

**GATE RECETTE NON-REGRESSION (R31+R32) :**
```bash
liaprobe --mode recette -f liaprobe/recette/datascan_recette.jsonl --output table
```
Score >= score precedent. Regression -> REVERT + REPLAN immediat.

Reference actuelle : **100.0% (5224/5224 effective, 0 MISS, 0 WRONG, 182 skipped)**
Cible finale : **100% (5406/5406)** -- loop jusqu'a atteinte.

Evaluation OBSERVE :
```
## Observation -- Post-Fix
Result: {score recette, confidence, FP count}
Expected: score >= 100.0%, confidence >= 0.90, FP = 0
Status: SUCCESS | PARTIAL (confidence < 0.90) | FAILURE (regression)
```

---

### REPLAN -- Sur chaque FAILURE

```
## Replan -- {TAXONOMY} Step {N}
Failure cause: {diagnostic}
Root cause category: PATTERN_BUG | ENGINE_BUG | DATA_MISSING | ENV_ISSUE | UNKNOWN
Alternatives:
  A. {approche A} -- rejetee car {raison}
  B. {approche B} -- selectionnee car {raison}
  C. {approche C} -- fallback si B echoue
New plan: {etapes mises a jour}
Impact sur autres sub-tasks: {changements en cascade}
```

Regles REPLAN :
- JAMAIS retenter la meme action sans changer au moins 1 variable
- 2 ports echouent sur meme cause -> fix moteur d'abord (R29)
- 2 REPLAN consecutifs (gate Konrad-Kurze, AVANT le 3eme) :
  - Invoquer `/konrad-kurze` via le Skill tool (model: **sonnet**) avec scope = `fingerprint-lab-improve/{taxonomy}/{step}`. Passer en evidence : decision_log.jsonl, dernieres captures pcap/banner, scores recette avant/apres.
  - Lire la directive emise dans `_alire/02_LOGS/Journals/meta/directives/KD-{id}.json`.
  - Si `risk_level = LOW` ET `injection.operation = ADD` ET `requires_approval = false` : appliquer comme 3eme alternative (par exemple : ajouter une source open-source non encore consultee, etendre la fenetre du capture pcap, varier l'angle d'attaque). Logger `action="KONRAD_DIRECTIVE_APPLIED"`.
  - Sinon : surface la directive a l'utilisateur en MEME temps que l'ESCALADE.

  Cas particulierement utiles :
  - GHOST_REDUNDANCY : on re-tente une variante du meme pattern qui a deja regresse au cycle precedent.
  - META_DATA_AMNESIA : la regle taxonomy n'a pas d'entree pour ce vendor/produit -> aucune cible a alimenter.
  - LEMANRUSS_TAINT : l'hypothese "PATTERN_BUG" est fausse, le vrai cause est ENGINE_BUG (et inversement) -- la categorie cause initiale a vicie tous les fix suivants.

- 3 REPLAN consecutifs -> escalade utilisateur L1 (avec la directive Konrad incluse si emise)
- Regression recette -> STOP, revert, REPLAN

---

### COMPLETE -- Rapport final (RETEX AFFICHE obligatoire)

```
## Completion Report
Objective: {fix TAXONOMY / improve detection rate}
Status: ACHIEVED | PARTIALLY_ACHIEVED | FAILED
Results:
  Recette score: {before} -> {after}
  Detection: {confidence}, FP: {count}
  REPLAN appliques: N
  Learnings: {regles RETEX ajoutees}
Next steps: {suggestions}
Agentic score: C1={}/10 C2={}/10 C3={}/10 C4={}/10 C5={}/10 Total={}/50
```

---

## Memoire 3 niveaux

**Working memory** (mise a jour apres chaque phase) :
```
## Working Memory
Completed: [steps]
Current: Step N -- role: EVALUATE
Pending: [steps restants]
Recette score: {latest}
Key findings: {resultats importants}
Blockers: {si applicable}
REPLAN count: N
```

**Long-term memory** : `_alire/02_LOGS/Journals/decision_log.jsonl` (append-only).

**Action journal** : 1 entree minimum par role (RESEARCH/EVALUATE/ACT/OBSERVE) par session.

---

## Tracabilite

| Fichier | Contenu |
|---------|---------|
| `_alire/02_LOGS/Journals/decision_log.jsonl` | Decision log (append-only) |
| `_alire/02_LOGS/Journals/retex/RETEX_FINGERPRINT_{YYYY-MM-DD}.md` | RETEX par session |
| `_alire/tracking/PLAN_LIAPROBE_DETECTION_{OBJECTIVE}_{YYYY-MM-DD}.md` | Plan persistant |
| `liaprobe/recette/live_results/QUAL_{TECHNO}_IP_{YYYY-MM-DD}.md` | Qualification live IPs |

Format decision log :
```json
{"timestamp":"ISO8601","session":"fingerprint-qual","action":"VERB","phase":"RESEARCH|EVALUATE|ACT|OBSERVE|REPLAN","step":N,"tool":"tool_name","input":"summary","output":"summary","status":"success|partial|failure","decision":"what_was_decided"}
```

---

## Contraintes (MANDATORY)

1. JAMAIS sauter une phase (RESEARCH->EVALUATE->ACT->OBSERVE)
2. JAMAIS deviner -- inspecter ou demander
3. JAMAIS retenter identiquement -- adapter au moins 1 variable
4. JAMAIS proceder sans logger
5. Quality gate = BLOQUANT, 0 exception
6. R12 : repos locaux d'abord, websearch OK pour le reste
7. R13 : scan apres disable FP obligatoire
8. R25 : lire 2+ repos locaux AVANT tout fix moteur
9. R29 : fix moteur 1:N > fix pattern 1:1
10. R30 : converter AVANT creation manuelle de 10+ patterns
11. R31+R32 : recette obligatoire apres fix moteur, score jamais en regression
12. R33 : agents interdits de `git add -A` -- lister explicitement les fichiers modifies
13. R34 : `datascan_recette.jsonl` = source de verite (5406 ground truth)

---

## Scripts et Converters

| Script | Usage |
|--------|-------|
| `scripts/scan_lab.sh [PORTS] [TIMEOUT]` | Full lab scan |
| `scripts/cleanup_fp.sh [--verify PORT]` | Disable known FP |
| `scripts/sync_fingerprints.sh <FILE\|--all>` | Sync lia/ -> by-taxonomy/ -> liaprobe/ |
| `scripts/tools/convert_recog_to_lia.py` | Batch Recog XML -> JSON (4662 fingerprints) |
| `scripts/tools/convert_nuclei_to_lia.py` | Nuclei YAML -> JSON |
| `scripts/tools/convert_wappalyzer_to_lia.py` | Wappalyzer -> JSON |
| `scripts/tools/convert_nmap_probes_to_lia.py` | Nmap probes -> JSON |

## Key Files

| File | Role |
|------|------|
| `data/fingerprints/lia/` | Source of truth patterns |
| `data/fingerprints/repositories/` | Local repos (reference, R25) |
| `liaprobe/pkg/agent/executor.go` | Executor (HTTPS, hostname, banner detect, protocol merge) |
| `liaprobe/pkg/fingerprint/matcher.go` | Matching (EvaluatePattern, required, multi-target banner) |
| `liaprobe/pkg/fingerprint/probe.go` | Probes HTTP/TCP (TLS, redirects, ParseHTTPBanner) |
| `liaprobe/pkg/fingerprint/loader.go` | Pattern loading (ByPort, ByTaxonomyName, pruning) |
| `liaprobe/recette/datascan_recette.jsonl` | Ground truth dataset (5406 cases) |
| `liaprobe/recette/live_targets.csv` | Live IPs for validation (45 targets) |

## References

| File | Content |
|------|---------|
| `references/code-exploration.md` | LiaProbe flow + open source + diagnose FP |
| `references/quality-gate.md` | Checklist per port + recurring FP + thresholds |
| `references/retex-rules.md` | Rules R1-R34 + pattern checklist |

---

## Scoring agentique (fin de session)

| ID | Critere | /10 |
|----|---------|-----|
| C1 | Decomposition (sub-tasks ecrits, deps, complexite, roles) | |
| C2 | Planification (PLAN_*.md + criteres succes/echec + selection outils) | |
| C3 | Observation (OBSERVE apres chaque action, Working Memory mise a jour) | |
| C4 | Replanification (diagnostic + 2+ alternatives, R25 repos lus, root cause category) | |
| C5 | Tracabilite (decision_log.jsonl, action journal avec roles, RETEX, recette score non-regression) | |

Score /50. Seuils : 40+ exemplaire, 30-39 acceptable, < 30 RETEX correctif obligatoire.
