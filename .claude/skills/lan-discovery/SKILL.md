---
name: lan-discovery
description: >
  Orchestre le pipeline complet de decouverte LAN pour audit CISO sur la plateforme LIA-SEC.
  Couvre : scan LiaProbe sur plages IP -> suivi progression -> inventaire assets -> fingerprinting
  technologies -> resolution scripts de collecte. Invoquer pour : lancer un scan sur un reseau
  client, exploiter l'inventaire apres scan, identifier les technologies, preparer la collecte LIA-Scan.
  Commandes : scan, status, inventory, fingerprint, collect.
user-invocable: true
argument-hint: "[scan <cible> | status <id> | inventory | fingerprint | collect <asset_id>]"
---

# LAN Discovery - Pipeline CISO

Orchestre les 5 etapes du pipeline de decouverte reseau LIA-SEC.

```
IP ranges ---> [1. Scan] ---> [2. Inventaire] ---> [3. Fingerprint] ---> [4. Collect] ---> LIA-Scan
               LiaProbe        asset_inventory       technologies          scripts PS1/SH
```

**Backend :** `http://localhost:8081` (ou `getBackendUrl()` depuis React)

---

## TRACABILITE AGENTIQUE (OBLIGATOIRE)

### Plan persistant
Creer `_alire/tracking/PLAN_LAN_DISCOVERY_{TARGET}_{YYYY-MM-DD}.md` (template: `_alire/tracking/PLAN_TEMPLATE.md`).

### Decision log
Logger dans `_alire/02_LOGS/Journals/decision_log.jsonl` les decisions non-triviales.
Format: `{"timestamp","session","action","reasoning","alternatives_rejected":[],"outcome","confidence","plan_ref"}`

### Replanification
Si 2 etapes echouent consecutivement → INVOQUER `/replan`.

### Scoring agentique (/50)
En fin de workflow, scorer sur : Decomposition, Planification, Replanification, Outillage dynamique, Tracabilite.

---

## ETAPE 1 -- `/lan-discovery scan <cible> [mode]`

Lancer un scan LiaProbe sur une ou plusieurs cibles.

```bash
# Plage CIDR
curl -s -X POST http://localhost:8081/api/discovery/scan/start \
  -H "Content-Type: application/json" \
  -d '{"targets":["192.168.1.0/24"],"scan_mode":"fast"}' | jq .

# IPs specifiques
curl -s -X POST http://localhost:8081/api/discovery/scan/start \
  -H "Content-Type: application/json" \
  -d '{"targets":["10.0.0.1","10.0.0.2","172.16.0.0/28"],"scan_mode":"thorough"}' | jq .

# Avec ports cibles
curl -s -X POST http://localhost:8081/api/discovery/scan/start \
  -H "Content-Type: application/json" \
  -d '{"targets":["192.168.0.0/24"],"ports":"22,80,443,3389,5985","scan_mode":"fast"}' | jq .
```

**Parametres :**

| Champ | Valeurs | Description |
|-------|---------|-------------|
| `targets` | `["IP","CIDR","FQDN"]` | Obligatoire. Tableau de cibles. |
| `scan_mode` | `fast` ou `thorough` | `fast` : ports top-1000 rapide. `thorough` : full L7 probes (plus lent). |
| `ports` | `"22,80,443"` | Optionnel. Restriction a ces ports seulement. |

La reponse contient `scan_id` (entier). Conserver pour l'etape suivi.

---

## ETAPE 2 -- `/lan-discovery status <scan_id>`

Suivre la progression d'un scan en cours.

```bash
# Status d'un scan
curl -s http://localhost:8081/api/discovery/scan/status/42 | jq .

# Historique de tous les scans
curl -s http://localhost:8081/api/discovery/scan/history | jq '.scans[] | {id, status, targets_count, started_at}'

# Resultats quand status=="completed"
curl -s http://localhost:8081/api/discovery/scan/results/42 | jq '.assets[] | {ip, hostname, technologies}'
```

**Champs status :** `running` | `completed` | `failed` | `stopped`

Afficher : progression (%), assets decouverts, technologies identifiees, duree.

---

## ETAPE 3 -- `/lan-discovery inventory [filtres]`

Interroger l'inventaire des assets apres scan.

```bash
# Lister tous les assets (pagine)
curl -s "http://localhost:8081/api/inventory/assets?limit=50&page=1" | jq .

# Filtrer par OS
curl -s "http://localhost:8081/api/inventory/assets?os_family=Windows&limit=100" | jq '.assets[] | {id, primary_ip, os_name, status}'

# Filtrer par criticite
curl -s "http://localhost:8081/api/inventory/assets?criticality=critical" | jq .

# Trier par derniere decouverte
curl -s "http://localhost:8081/api/inventory/assets?sort_by=last_seen&sort_order=desc" | jq .

# Detail complet d'un asset (avec technologies + services + sources)
curl -s http://localhost:8081/api/inventory/assets/<uuid> | jq .
```

**Parametres de liste :**

| Param | Exemple | Description |
|-------|---------|-------------|
| `limit` | `50` | Assets par page (defaut 50) |
| `page` | `1` | Numero de page |
| `search` | `"dc01"` | Recherche IP/hostname |
| `os_family` | `"Windows"` | Filtre OS |
| `criticality` | `"critical"` | critical / high / medium / low |
| `status` | `"active"` | active / inactive / unknown |
| `sort_by` | `"last_seen"` | last_seen / primary_ip / os_family |
| `sort_order` | `"desc"` | asc / desc |

**UI :** Discovery > Inventory tab. Colonnes triables, multi-select, export CSV.

---

## ETAPE 4 -- `/lan-discovery fingerprint`

Lancer le fingerprinting sur tous les assets de l'inventaire pour identifier les technologies.

```bash
# Lancer le fingerprinting batch
curl -s -X POST http://localhost:8081/api/inventory/fingerprint/run \
  -H "Content-Type: application/json" \
  -d '{}' | jq .

# Verifier les technologies identifiees
curl -s http://localhost:8081/api/inventory/technologies | jq '.technologies[] | {taxonomy_code, count}'

# Dashboard de couverture audit
curl -s http://localhost:8081/api/inventory/dashboard/coverage | jq '.items[] | {taxonomy_code, asset_count, has_rules}'
```

**Note :** Le fingerprinting utilise les 15 719 patterns LiaProbe (sources : LIA + Nmap + Recog + Nuclei + Wappalyzer). Priorite : lia(100) > nmap(80) > recog(60) > nuclei(50) > wappalyzer(40).

---

## ETAPE 5 -- `/lan-discovery collect <asset_id>`

Resoudre les scripts de collecte applicables pour un asset (en fonction de ses technologies).

```bash
# Resoudre les scripts pour un asset
curl -s -X POST http://localhost:8081/api/inventory/assets/<uuid>/launch-collection | jq .

# Resultat type :
# {
#   "asset_id": "...",
#   "asset_ip": "10.0.0.5",
#   "scripts": [
#     {"script_name": "Collect-AD-Users.ps1", "script_type": "ps1", "taxonomy_code": "ADDS", ...},
#     {"script_name": "Collect-AD-Groups.ps1", "script_type": "ps1", "taxonomy_code": "ADDS", ...}
#   ],
#   "total": 8
# }
```

**Afficher le resultat :** lister les scripts regroupes par type (PS1 / SH), avec la taxonomie et le chemin `scripts/collect/`.

**UI :** Cliquer sur un asset > onglet Technologies > bouton "Resolve scripts".

---

## WORKFLOW COMPLET CISO

Voir [references/workflow.md](references/workflow.md) pour le workflow detaille avec validations.

---

## REPONSE TYPE

Apres `/lan-discovery scan` :
```
Scan lance : ID #42
Cibles : 192.168.1.0/24 (254 hosts)
Mode : fast
Suivi : GET /api/discovery/scan/status/42

Prochain : /lan-discovery status 42
```

Apres `/lan-discovery collect` :
```
Asset : 10.0.0.5 (ADDS + DOCKER)
Scripts resolus : 12

Type  Technologie  Script
PS1   ADDS         Collect-AD-Users.ps1
PS1   ADDS         Collect-AD-Groups.ps1
PS1   ADDS         Collect-AD-GPO.ps1
SH    DOCKER       collect_docker_images.sh
...

Chemin : scripts/collect/active_directory/ | scripts/collect/docker/
Etape suivante : executer ces scripts sur la cible puis lancer LIA-Scan.
```

---

## VERIFICATION GATE DISCOVERY (BLOQUANT)

Apres chaque operation du pipeline, AVANT de declarer "termine" :

1. **STORAGE GATE** : Verifier que les resultats du scan sont stockes en PostgreSQL :
   ```bash
   sudo -u postgres psql -d lia_scan -c "SELECT count(*) FROM asset_inventory WHERE scan_id = <id>;"
   ```
   Le count doit etre > 0 si des assets ont ete decouverts.
2. **FINGERPRINT GATE** : Apres fingerprinting, verifier le mapping taxonomie :
   ```bash
   curl -s http://localhost:8081/api/inventory/technologies | jq '.technologies | length'
   ```
   Le nombre de technologies identifiees doit etre > 0.
3. **HEALTH GATE** : Verifier que le backend repond toujours apres la charge du scan :
   ```bash
   curl -sf http://localhost:8081/api/health | jq .status
   ```
   Doit retourner `"ok"`. Si timeout ou erreur : le scan a surcharge le backend.
4. **BUILD GATE** : Si du code Go/React a ete modifie pendant l'operation :
   `bash cmd/sigma_web/build_secure_lia.sh` (Go) + `cd sigma-react-frontend && node node_modules/.bin/vite build` (React)

Si une gate echoue : STOP, diagnostiquer, corriger, re-gate. JAMAIS declarer "termine" sans les gates vertes.
Incident de reference : 188 fichiers casses par imports manquants (2026-03-17) -- meme discipline pour le pipeline discovery.
