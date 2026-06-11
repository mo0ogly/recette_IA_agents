---
name: recette-banner
description: Recette de validation des banners du banner-server (COUCHE 5) v5.0 -- boucle autonome VALIDATE->EVALUATE->FIX->LOOP. Probe direct + scan LiaProbe, verdict SUCCESS/PARTIAL/FAILURE apres chaque action, REPLAN sur FAILURE avec 2+ alternatives, RETEX affiche obligatoire. Triggers sur "recette-banner", "valide les banners", "test banner", "probe banner".
---

# Skill : recette-banner v5.0

Boucle autonome de validation banner : VALIDATE -> EVALUATE -> FIX -> re-VALIDATE -> LOOP or COMPLETE.

## Chemins critiques

```bash
PROJECT_ROOT="/home/mo0ogly/Bureau/vscode_lia_audit"
BANNER_DIR="$PROJECT_ROOT/docker/discovery-lab/banner-server/banner_analysis"
BANNERS_JSON="$PROJECT_ROOT/docker/discovery-lab/banner-server/banners.json"
BANNER_STATE="$PROJECT_ROOT/docker/discovery-lab/banner-server/banner_state.json"
BANNER_MENU="$PROJECT_ROOT/docker/discovery-lab/banner-server/banner_menu.sh"
BANNER_SERVER_IP="172.30.0.33"
```

## Model Selection

| Phase | Model | Rationale |
|-------|-------|-----------|
| VALIDATE (probe/scan) | `haiku` | Script execution, nc/curl commands |
| EVALUATE (verdict) | `haiku` | Comparison logic, score calculation |
| FIX (pattern) | `sonnet` | Pattern fix requires code understanding |
| RETEX | `haiku` | Report generation, file operations |

FIX est le seul role qui justifie sonnet.

## Outil principal : banner_menu.sh

```bash
cd docker/discovery-lab/banner-server
./banner_menu.sh list [CATEGORIE]         # RESEAU|WEB|SSH_TELNET|MAIL|PROTOCOLES|ICS_SCADA
./banner_menu.sh enable|disable {id}
./banner_menu.sh rebuild                  # Regenerer banners.json + restart
./banner_menu.sh recette {id}|all         # Recette unitaire ou globale
./banner_menu.sh report
./banner_menu.sh status
```

> See [references/banner-inventory.md](references/banner-inventory.md) pour l'inventaire complet des 30 banners, les causes de SKIP LiaProbe, et le workflow de validation de nouveaux banners.

---

## Boucle autonome (MANDATORY)

```
PRE-CHECK -> [VALIDATE -> EVALUATE -> FIX?] x N banners -> COMPLETE
                   ^______________|
                   LOOP si FAILURE ou MISMATCH
```

### PRE-CHECK

```bash
./banner_menu.sh status
# Si inactif :
cd docker/discovery-lab && docker-compose up -d --no-deps banner-server && sleep 3
```

Evaluation: SUCCESS (banner-server repond) | FAILURE -> REPLAN (docker down / reseau).

---

### VALIDATE -- Probe direct

```bash
./banner_menu.sh recette {id}
# Ou : bash banner_analysis/{id}/probe.sh
```

Verdict probe : PASS (banner + pattern) | WARN (banner, pas pattern) | FAIL (pas de reponse).

### VALIDATE -- Scan LiaProbe

```bash
curl -s -X POST http://localhost:8081/api/discovery/scan/start \
  -H "Content-Type: application/json" \
  -d '{"targets":["172.30.0.33"],"ports":"9001","scan_mode":"thorough"}'
# IMPORTANT : ports en CSV ("9001,9002"), JAMAIS en range ("9001-9023")
```

Lire resultats :
```bash
SCAN_ID=$(curl -s http://localhost:8081/api/discovery/scans | python3 -c "
import json,sys; scans=json.load(sys.stdin); print(sorted(scans,key=lambda x:x.get('id',0))[-1]['id'])")
curl -s "http://localhost:8081/api/discovery/scan/results/$SCAN_ID"
```

**QH-B1 (BLOCKING)**: resultats non-vides obligatoires avant EVALUATE.

---

### EVALUATE -- Verdict par banner

| Probe | LiaProbe | Verdict | Action |
|-------|----------|---------|--------|
| PASS | PASS taxonomy match | SUCCESS | LOOP next banner |
| PASS | PASS + version | SUCCESS+ | LOOP next banner |
| PASS | null (pas scanne) | PARTIAL | Accept, log, LOOP next |
| PASS | SKIP | PARTIAL_SCAN_SKIP | Accept (cause connue), LOOP next |
| PASS | FAIL taxonomy KO | FAILURE | -> FIX pattern |
| FAIL | N/A | FAILURE | -> FIX probe/port |

Ecrire `PROBE_{YYYYMMDD}_{HHMMSS}.json` dans `banner_analysis/{id}/recette/`.

**QH-B2 (BLOCKING)**: champs requis dans PROBE JSON : `id`, `taxonomy`, `port`, `verdict`.

---

### FIX -- Correction pattern (si EVALUATE = FAILURE)

**Escalade stricte : JAMAIS de fix autonome sur pattern ou code Go.**

FIX pattern JSON : SUPERVISED (modifie le moteur fingerprint).
FIX isHTTPPort / hints : SUPERVISED (modifie code Go).
FIX rebuild + restart : SUPERVISED (impacte prod).

Workflow FIX :
1. Identifier la cause racine (pattern manquant, mauvais taxonomy, isHTTPPort absent)
2. Consulter [references/banner-inventory.md](references/banner-inventory.md) pour causes SKIP connues
3. Proposer le fix avec 2 alternatives minimum
4. Appliquer apres confirmation
5. Rebuild :
   ```bash
   cd cmd/sigma_web && ./build_secure_lia.sh
   ```
6. **QH-B3 (BLOCKING)**: build passe AVANT de re-VALIDATE
7. **QH-B4 (BLOCKING)**: banner-server repond, health OK apres rebuild

Apres FIX -> retour VALIDATE (re-probe + re-scan du banner corrige).

---

### REPLAN -- Sur chaque FAILURE

```
## Replan -- Banner {id}
Failure cause: {diagnostic}
Root cause: PATTERN_BUG | ENGINE_BUG | PORT_MISSING | ENV_ISSUE | KNOWN_SKIP
Alternatives:
  A. {approche A} -- rejetee car {raison}
  B. {approche B} -- selectionnee car {raison}
  C. {approche C} -- fallback si B echoue
```

Regles de REPLAN :
- JAMAIS retenter la meme action sans changer au moins 1 variable
- 2+ banners echouent sur meme cause -> fix batch (ex: isHTTPPort manquant)
- Fix pattern ne corrige pas : STOP -> alternative (hint, taxonomy, port hints)
- JAMAIS empiler les fixes sans rebuild intermediaire (globalPatternIndex = singleton)
- 3 REPLAN consecutifs sans succes -> escalade utilisateur

---

### COMPLETE -- Fin de boucle

```
RETEX - recette-banner ({DATE})
Banners: N total, X SUCCESS, Y PARTIAL, Z FAILURE, W MISMATCH
| ID | Taxonomy | Port | Probe | LiaProbe | Verdict |
...
Score: XX% (SUCCESS+PARTIAL) / total
Seuil production: >= 80% SUCCESS requis
REPLAN appliques: N
Fixes commites: oui/non
```

**RETEX AFFICHE obligatoire** -- meme si score 100%.

---

## Seuils de scoring

| Score | Verdict | Action |
|-------|---------|--------|
| 100% SUCCESS | Excellent | Production ready |
| >= 80% SUCCESS | Bon | SKIP acceptables |
| 50-79% | Moyen | Review patterns |
| < 50% | Mauvais | Banner-server ou patterns a corriger |

---

## Gestion banner_state.json

```bash
./banner_menu.sh disable lia-nginx && ./banner_menu.sh rebuild
# Coherence check :
python3 -c "
import json, os
state = json.load(open('banner_state.json'))
missing = set(os.listdir('banner_analysis')) - set(state.keys())
print('Manquants:', missing)
"
```

**Nouveau banner :** TOUJOURS ajouter dans `banner_state.json` sinon rebuild le supprime.

---

## Memoire 3 niveaux

**Working memory** (mise a jour apres chaque banner) :
```
Completed: [id1, id2]
Current: id3 -- EVALUATE en cours
Pending: [id4..idN]
REPLAN count: 2
Fixes applied: [{id, fix_type}]
```

**Long-term memory** : `banner_analysis/{id}/recette/action_journal.jsonl` par banner.

**Action journal** (decision_log.jsonl) : choix non-triviaux (fix pattern, hint, isHTTPPort).

---

## Tracabilite

- Plan : `_alire/tracking/PLAN_RECETTE_BANNER_{BANNER}_{YYYY-MM-DD}.md`
- Decision log : `_alire/02_LOGS/Journals/decision_log.jsonl`
- Action journal : `banner_analysis/{id}/recette/action_journal.jsonl`
- PROBE JSON : `banner_analysis/{id}/recette/PROBE_{YYYYMMDD}_{HHMMSS}.json`

---

## Scoring agentique (fin de workflow)

| Critere | Score |
|---------|-------|
| C1 Decomposition : banners identifies, dependances mappees | /10 |
| C2 Planification : PLAN_*.md cree et suivi | /10 |
| C3 Replanification : REPLAN sur chaque FAILURE avec 2+ alternatives | /10 |
| C4 Outillage : banner_menu.sh + API LiaProbe + build_secure_lia.sh | /10 |
| C5 Tracabilite : PROBE JSON + decision_log + RETEX affiche | /10 |

**Total /50** -- >= 40 Exemplaire | 30-39 Acceptable | < 30 RETEX obligatoire

---

## Fichiers de reference

| Fichier | Contenu |
|---------|---------|
| [references/banner-inventory.md](references/banner-inventory.md) | 30 banners, causes SKIP, validation nouveau banner, debug |
| `docker/discovery-lab/banner-server/banner_menu.sh` | Script menu principal |
| `docker/discovery-lab/banner-server/banner_state.json` | Etat actif/inactif |
| `cmd/sigma_web/discovery_scanner_engine.go` ~1285 | isHTTPPort() |
| `cmd/sigma_web/fingerprint_port_hints.go` | PortServiceHints |
| `data/fingerprints/lia/` | Patterns fingerprint LIA |
