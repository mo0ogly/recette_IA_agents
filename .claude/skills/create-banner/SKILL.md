---
name: create-banner
description: >
  Cree une banniere pour le banner-server du Discovery Lab (COUCHE 5) v5.0 agentic loop.
  Loop autonome: OBJECTIVE -> RESEARCH -> ACT -> OBSERVE -> EVALUATE -> REPLAN? -> LOOP or COMPLETE.
  Se declenche sur "create-banner", "ajoute un banner", "nouvelle banniere", "banner-server".
---

# Skill : create-banner v5.0

Cree et valide une banniere synthetique pour le banner-server Discovery Lab (COUCHE 5).

## Declenchement

Utiliser quand :
- Valider un pattern fingerprint LIA via une banniere synthetique
- Ajouter un service au banner-server (equipement reseau, protocole, serveur)
- Tester la detection LiaProbe sans deployer le vrai service Docker
- Le service cible n'a pas d'image Docker ARM64

Ne PAS utiliser quand :
- Le service a une image Docker officielle ARM64 -> `/create-lab-banner`
- Executer les recettes existantes -> `/recette-banner`

## Pre-requis

1. Discovery Lab operationnel : `cd docker/discovery-lab && ./lab.sh status`
2. Backend LIA-Scan sur port 8081
3. Fichier fingerprint dans `data/fingerprints/lia/{TAXONOMY}.json`
4. Port disponible dans la plage 9001-9099+

References a lire :
- `_alire/01_DOCUMENTATION/discovery/BANNER_CREATION_GUIDE.md`
- `docker/discovery-lab/banner-server/banner_analysis/` (exemples existants)

## Arguments

- `$ARGUMENTS[0]` - Taxonomy LIA (4 lettres) ou ID banner existant (ex: `CISC`, `lia-cisco-ssh`)
- `--port PORT` - Port specifique (optionnel, auto-incremente sinon)

Commandes speciales :
- `/create-banner list [categorie]` - Lister (reseau|ssh|mail|web|protocoles|ics|databases)
- `/create-banner enable|disable {id}` - Activer/desactiver dans banner_state.json
- `/create-banner status` - Etat du banner-server
- `/create-banner scan` - Scanner tous les ports avec LiaProbe
- `/create-banner build` - Regenerer banners.json + rebuild + restart
- `/create-banner report` - Tableau synthese des dernieres recettes
- `/create-banner docs` - Regenerer RECETTE_INDEX.md + README manquants

Menu interactif : `cd docker/discovery-lab/banner-server && ./banner_menu.sh`

---

## Chemins critiques

```bash
PROJECT_ROOT="/opt/lia-sec/dev"
BANNER_DIR="$PROJECT_ROOT/docker/discovery-lab/banner-server/banner_analysis"
BANNERS_JSON="$PROJECT_ROOT/docker/discovery-lab/banner-server/banners.json"
BANNER_STATE="$PROJECT_ROOT/docker/discovery-lab/banner-server/banner_state.json"
BANNER_SERVER_IP="172.30.0.33"
```

---

## Boucle Agentique v5.0

```
OBJECTIVE
  -> identifier technology + trouver banniere reelle
RESEARCH (sonnet)
  -> sources: patterns convertis / doc officielle / WebSearch
  -> EXIT si banniere non trouvee apres 3 sources: ESCALATE
ACT (haiku)
  -> creer banner_analysis/ (5 elements) + deployer
OBSERVE (haiku)
  -> executer probe.sh + lancer scan LiaProbe
EVALUATE
  -> SUCCESS: taxonomy correcte + confidence >= 0.60 -> COMPLETE
  -> PARTIAL: confidence >= 0.40 -> documenter, COMPLETE avec avertissement
  -> FAILURE: taxonomy incorrecte ou confidence < 0.40 -> REPLAN
REPLAN (sur chaque FAILURE)
  -> alternative 1: changer type banniere (tcp_init -> hex_respond)
  -> alternative 2: corriger pattern fingerprint (banner_matchers)
  -> alternative 3: ajouter port dans PortServiceHints / isHTTPPort()
  -> LOOP avec nouvelle approche
  -> apres 3 FAILURE consecutifs: ESCALATE (modifie code Go, hors scope)
COMPLETE
  -> RETEX AFFICHE obligatoirement
```

### Model Selection

| Phase | Model | Raison |
|-------|-------|--------|
| RESEARCH (source banniere) | `sonnet` | Web research + raisonnement sur sources |
| ACT / OBSERVE / REPLAN | `haiku` | Creation fichiers, execution scripts |

---

## Quality Hooks

| Hook | Condition bloquante |
|------|-------------------|
| QH-B1 Post-RESEARCH | `analyse/RECOG_SOURCE.md` existe avec source documentee |
| QH-B2 Post-ACT | 5 elements canoniques presents (banner.json, probe.sh, recette/, analyse/, RECOG_SOURCE.md) |
| QH-B3 Post-OBSERVE | PROBE_*.json existe avec probe_status != FAIL |
| QH-B4 Post-EVALUATE | FINGERPRINT_ANALYSIS.md a jour, verdict documente |

---

## Phase RESEARCH (GATE BLOQUANTE)

**Objective :** Trouver la banniere exacte avec source documentee.

**Priorite de recherche :**

1. Patterns convertis existants :
```python
python3 -c "
import json
fp = json.load(open('data/fingerprints/lia/{TAXONOMY}.json'))
for m in fp.get('banner_matchers', []):
    print(f\"  type={m.get('type','?')} value={m.get('value','')[:120]}\")
"
```

2. Doc officielle du service (format protocole : SSH, FTP, SMTP, POP3, IMAP, VNC)

3. WebSearch fallback : `{technology} banner TCP response default`

**Determiner le type de banniere** (4 types : `tcp_init`, `tcp_respond`, `http`, `hex_respond`)

> Arbre de decision et templates : [references/banner-types-templates.md](references/banner-types-templates.md)

**Livrable RESEARCH :** `analyse/RECOG_SOURCE.md` avec banniere exacte + type + justification.

**EVALUATE RESEARCH :**
- SUCCESS : banniere documentee avec source verifiable -> ACT
- FAILURE : aucune source apres 3 tentatives -> ESCALATE (hors scope skill)

---

## Phase ACT

**2.1 - Trouver le prochain port libre**

```python
import json
with open("docker/discovery-lab/banner-server/banners.json") as f:
    ports = sorted([e["port"] for e in json.load(f)])
next_port = max(ports) + 1 if ports else 9001
```

**2.2 - Nommer l'ID** : `lia-{taxonomy_lower}[-qualifier]`

**2.3 - Creer l'arborescence**

```bash
BASE="docker/discovery-lab/banner-server/banner_analysis"
ID="lia-{taxonomy_lower}"
mkdir -p "$BASE/$ID/recette" "$BASE/$ID/analyse"
```

**2.4 - Ecrire banner.json + probe.sh**

> Templates par type : [references/banner-types-templates.md](references/banner-types-templates.md)

**2.5 - Deployer**

```bash
python3 scripts/tools/build_banners_json.py
cd docker/discovery-lab && docker-compose -f docker-compose.yml up -d --build banner-server
sleep 3
nc -zv localhost {PORT}
```

**EVALUATE ACT :**
- SUCCESS : port actif, 5 elements presents -> OBSERVE
- FAILURE : port inactif ou elements manquants -> REPLAN (alt: corriger banner.json)

---

## Phase OBSERVE

```bash
# Executer probe.sh
bash docker/discovery-lab/banner-server/banner_analysis/{id}/probe.sh
# Generer recette/PROBE_YYYYMMDD_HHMMSS.json

# Scanner avec LiaProbe (CSV obligatoire, pas ranges)
curl -s -X POST http://localhost:8081/api/discovery/scan/start \
  -H "Content-Type: application/json" \
  -d '{"targets":["172.30.0.33"],"ports":"{PORT}","scan_mode":"thorough"}'
```

> Format PROBE JSON et procedures debugging : [references/banner-types-templates.md](references/banner-types-templates.md) + [references/research-and-debugging.md](references/research-and-debugging.md)

---

## Phase EVALUATE

| Verdict | Condition | Decision |
|---------|-----------|----------|
| SUCCESS | taxonomy correcte + confidence >= 0.60 | COMPLETE |
| PARTIAL | taxonomy correcte + confidence >= 0.40 | COMPLETE avec avertissement |
| FAILURE | taxonomy incorrecte ou confidence < 0.40 | REPLAN |
| SKIP | Pattern non indexe | REPLAN (alt: corriger globalPatternIndex) |

---

## Phase REPLAN (sur chaque FAILURE)

Documenter le failure dans `decision_log.jsonl`, puis choisir parmi :

**Alternative 1** : Changer le type de banniere
- tcp_init -> hex_respond si le service utilise un handshake binaire
- tcp_respond si la banniere n'est envoyee qu'apres trigger

**Alternative 2** : Corriger le pattern fingerprint
- Verifier `banner_matchers` dans `data/fingerprints/lia/{TAXONOMY}.json`
- Rebuild + restart obligatoire apres modification JSON :
```bash
cd cmd/sigma_web && ./build_secure_lia.sh
./cleanup_services.sh backend
```
Note : fix pattern = SUPERVISED (modifie moteur)

**Alternative 3** : Ajouter port dans hints
- `isHTTPPort()` ou `PortServiceHints` dans le code Go
- Note : modification Go = APPROVAL_REQUIRED

**Apres 3 FAILURE consecutifs :** ESCALATE - fix necessite une modification du code Go, hors scope autonome.

---

## Gestion de l'etat (banner_state.json)

`true` = actif, `false` = inactif. Le rebuild filtre par cet etat.

```bash
./banner_menu.sh enable lia-mssql
./banner_menu.sh disable lia-modbus
```

---

## RETEX (AFFICHE OBLIGATOIREMENT en fin de loop)

```
RETEX create-banner {TAXONOMY} {DATE}
Iterations : {N}
Verdict final : SUCCESS / PARTIAL / FAILURE
Banniere : {type} sur port {PORT}
Source : {RECOG_SOURCE ou WebSearch ou doc officielle}
Confidence LiaProbe : {valeur}
Alternatives testees : {liste}
Tracabilite : PLAN_BANNER_{TAXONOMY}_{DATE}.md + decision_log.jsonl
```

---

## Decomposition des sous-taches

Au demarrage, decomposer la demande en sous-taches independantes :

- [ ] Sous-tache 1 : Phase RESEARCH -- banniere exacte + source documentee (RECOG_SOURCE.md)
- [ ] Sous-tache 2 : Phase ACT -- creer arborescence banner_analysis/ (5 elements) + deployer
- [ ] Sous-tache 3 : Phase OBSERVE -- executer probe.sh + scan LiaProbe
- [ ] Sous-tache 4 : Phase EVALUATE -- verdict SUCCESS/PARTIAL/FAILURE
- [ ] Sous-tache 5 : mise a jour FINGERPRINT_ANALYSIS.md + banners.json + RETEX

Utiliser `TaskCreate` pour tracker si > 3 sous-taches.

## Plan d'execution

Pour toute creation de banniere :

1. Creer `_alire/tracking/PLAN_BANNER_{TAXONOMY}_{YYYY-MM-DD}.md` au demarrage (avant toute ecriture).
2. Template : `_alire/tracking/PLAN_TEMPLATE.md`.
3. Cocher chaque sous-tache a la completion.
4. Si replanification : Status -> REPLANIFIE + lien vers nouveau plan.

Pour une correction ponctuelle (pattern seul, < 2 fichiers) : plan inline suffit.

## Outils declares

| Outil | Usage | Retry policy |
|-------|-------|--------------|
| `Read`, `Bash python3` | Lire fingerprints existants + lister ports banners.json | N/A |
| `Write`, `Edit` | Creer banner.json, probe.sh, RECOG_SOURCE.md, FINGERPRINT_ANALYSIS.md | N/A |
| `Bash nc` / `Bash docker-compose` | Deployer et verifier port actif (Phase ACT) | 1 retry |
| `Bash probe.sh` | Executer probe et capturer PROBE_*.json (Phase OBSERVE) | N/A |
| `Bash curl /api/discovery/scan/start` | Scanner avec LiaProbe (CSV obligatoire) | N/A |
| `WebSearch` | Trouver banniere exacte si patterns convertis insuffisants (niveau 3) | N/A |
| `Bash build_secure_lia.sh` | Rebuild si correction pattern fingerprint .json | Obligatoire si alt-2 |
| `TaskCreate` | Tracking si > 3 sous-taches | N/A |

Selection dynamique : outil choisi selon le contexte, pas de liste figee.

## Tracabilite (OBLIGATOIRE)

Creer `_alire/tracking/PLAN_BANNER_{TAXONOMY}_{YYYY-MM-DD}.md` au demarrage.

Logger dans `_alire/02_LOGS/Journals/decision_log.jsonl` :
```bash
echo '{"timestamp":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","session":"create-banner-{TAXONOMY}","action":"ACTION","reasoning":"...","alternatives_rejected":["..."],"outcome":"SUCCESS|FAILURE","confidence":"high|medium|low","plan_ref":"PLAN_BANNER_{TAXONOMY}_{DATE}.md"}' >> _alire/02_LOGS/Journals/decision_log.jsonl
```

Apres completion :
- Mettre a jour `_alire/tracking/FINGERPRINTING_ENGINE_2026-02-28.md` (compteur LIA patterns)

---

## Definition of Done

- [ ] `analyse/RECOG_SOURCE.md` existe
- [ ] `banner.json` JSON valide
- [ ] `probe.sh` executable, retourne PASS
- [ ] `recette/PROBE_*.json` avec resultats
- [ ] `analyse/FINGERPRINT_ANALYSIS.md` existe
- [ ] `banners.json` regenere
- [ ] Banner-server redeploy, port actif
- [ ] LiaProbe detecte la taxonomy (confidence >= 0.60 PASS, >= 0.40 PARTIAL acceptable)

---

## VERIFICATION GATE (BLOQUANT)

Apres execution, AVANT de declarer termine :

- [ ] `analyse/RECOG_SOURCE.md` existe avec source documentee (URL ou doc officielle)
- [ ] 5 elements canoniques presents : banner.json, probe.sh, recette/, analyse/, RECOG_SOURCE.md
- [ ] Port actif : `nc -zv localhost {PORT}` repond
- [ ] `recette/PROBE_*.json` existe avec probe_status != FAIL
- [ ] LiaProbe detecte la taxonomy (confidence >= 0.60 PASS, >= 0.40 PARTIAL acceptable)
- [ ] `banners.json` regenere via `build_banners_json.py`
- [ ] `analyse/FINGERPRINT_ANALYSIS.md` a jour avec verdict
- [ ] RETEX affiche dans le chat (OBLIGATOIRE)
- [ ] `decision_log.jsonl` loge chaque alternative testee

Si un gate echoue : STOP, REPLAN (choisir alt-1/2/3), re-gate. JAMAIS declarer "done" avec confidence < 0.40.

## Scoring agentique

| Critere | Score |
|---------|-------|
| C1 Decomposition : sous-taches identifiees (RESEARCH / ACT / OBSERVE / EVALUATE) ? | /10 |
| C2 Planification : PLAN_BANNER_*.md cree et suivi ? | /10 |
| C3 Replanification : /replan declenche sur echecs consecutifs (3 FAILURE) ? | /10 |
| C4 Outillage : patterns lus + probe.sh + curl LiaProbe + WebSearch invoques dynamiquement ? | /10 |
| C5 Tracabilite : decision_log + RETEX produits ? | /10 |

Score total /50 -- >= 40 : Exemplaire | 30-39 : Acceptable | < 30 : RETEX obligatoire

---

## Commandes utiles

```bash
# Tableau bannieres existantes
python3 -c "
import json
with open('docker/discovery-lab/banner-server/banners.json') as f:
    entries = json.load(f)
for e in sorted(entries, key=lambda x: x['port']):
    print(f\"{e['id']:<24} {e.get('taxonomy','?'):<8} {e['port']:<6} {e.get('type','?'):<12}\")
"

# Regenerer + redemarrer
python3 scripts/tools/build_banners_json.py
cd docker/discovery-lab && docker-compose up -d --build banner-server

# Scanner un port (CSV obligatoire)
curl -s -X POST http://localhost:8081/api/discovery/scan/start \
  -H "Content-Type: application/json" \
  -d '{"targets":["172.30.0.33"],"ports":"9001","scan_mode":"thorough"}'
```

> Inventaire complet : [references/banner-inventory.md](references/banner-inventory.md)
> Templates et formats : [references/banner-types-templates.md](references/banner-types-templates.md)
> Research et debugging : [references/research-and-debugging.md](references/research-and-debugging.md)

*Skill v5.0 - 2026-04-04 - Agentic loop architecture*
