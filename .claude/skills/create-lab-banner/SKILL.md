---
name: create-lab-banner
description: Ajoute une nouvelle technologie au Discovery Lab v5.0 agentic loop. Recherche internet obligatoire pour la banniere exacte. Cree le service Docker/tcpbanner/http, teste la detection LiaProbe, produit une PREUVE DE RECETTE tracable. Loop autonome jusqu'a detection correcte ou escalade.
---

# Skill : create-lab-banner v5.0

Ajoute une technologie au Discovery Lab pour valider les patterns fingerprint LIA-Scan.
**Chaque ajout produit une preuve de recette persistante** dans `docker/discovery-lab/recette/`.

---

## Boucle Agentique v5.0

```
OBJECTIVE
  -> identifier technologie + type de service (docker/tcpbanner/http)
RESEARCH (sonnet)
  -> banniere reelle: nmap-service-probes / patterns existants / WebSearch / Docker Hub
  -> EXIT si aucune banniere apres 3 sources: ESCALATE
ACT (haiku)
  -> creer service Docker ou config tcpbanner ou app http
  -> demarrer lab + capturer banniere reelle
OBSERVE (haiku)
  -> scan LiaProbe + logs PostgreSQL fingerprinting
EVALUATE
  -> SUCCESS: taxonomy correcte + confidence >= 0.60 -> ecrire preuve -> COMPLETE
  -> PARTIAL: taxonomy correcte + pas de version -> documenter -> COMPLETE
  -> FAILURE: taxonomy incorrecte ou confidence < 0.60 -> REPLAN
REPLAN (sur chaque FAILURE)
  -> alternative 1: image Docker absente ARM64 -> basculer tcpbanner ou http
  -> alternative 2: banniere TCP vide -> tester HTTP probe ou ajouter delai connexion
  -> alternative 3: pattern fingerprint absent -> invoquer /create-banner (COUCHE 5)
  -> LOOP avec nouvelle approche
  -> apres 3 FAILURE: ESCALATE
COMPLETE
  -> ecrire preuve JSON + RECETTE_INDEX.md
  -> RETEX AFFICHE obligatoirement
```

### Model Selection

| Phase | Model | Raison |
|-------|-------|--------|
| RESEARCH (banniere + image ARM64) | `sonnet` | Web research, evaluation sources |
| ACT / OBSERVE / REPLAN / LIBRARIAN | `haiku` | Creation fichiers, execution commandes |

---

## Quality Hooks

| Hook | Condition bloquante |
|------|-------------------|
| BANNER_REAL_CHECK | Avant ACT: banniere vient d'une source reelle, pas inventee |
| PATTERN_EXISTS_CHECK | Avant OBSERVE: verifier pattern fingerprint pour cette techno (WARNING si absent) |
| SCAN_VERDICT_GATE | Apres OBSERVE: taxonomy correcte + confidence >= 0.60 = SUCCESS |
| PROOF_WRITTEN_GATE | Avant COMPLETE: fichier JSON preuve + RECETTE_INDEX.md mis a jour |

---

## Pre-requis

- Discovery Lab operationnel : `docker/discovery-lab/lab.sh status`
- Backend LIA-Scan sur port 8081
- Patterns fingerprint charges : `curl localhost:8081/api/fingerprints/status`

---

## Phase RESEARCH (GATE BLOQUANTE)

**Rechercher la banniere EXACTE du service. Aucune valeur inventee.**

Sources par priorite :
1. `grep -A5 "p/{product}/" /usr/share/nmap/nmap-service-probes`
2. Patterns existants : `ls data/fingerprints/*/{TAXONOMY}*.json`
3. WebSearch : `{technology} banner TCP response default`
4. Documentation officielle : headers HTTP, formats de reponse
5. Docker Hub : image officielle avec tag de version specifique

**Choisir le type de service :**

| Type | Quand | Exemple |
|------|-------|---------|
| `docker` | Image Docker officielle disponible en arm64 | Tomcat, Prometheus, RabbitMQ |
| `tcpbanner` | Pas d'image Docker, banniere TCP simple | Cisco IOS, FortiGate, HP iLO |
| `http` | Application web avec headers/HTML specifiques | Interface admin custom |

Verification ARM64 :
```bash
docker manifest inspect IMAGE:TAG 2>/dev/null | grep -c '"arm64"'
```

**EVALUATE RESEARCH :**
- SUCCESS : banniere documentee + type choisi -> ACT
- FAILURE : aucune banniere apres toutes les sources -> ESCALATE

---

## Phase ACT

#### Type `docker`

Ajouter dans `docker/discovery-lab/docker-compose.apps.yml` :

```yaml
  {service_name}:
    image: {image}:{tag}
    container_name: lab-{service_name}
    hostname: {hostname}
    environment:
      - {ENV_VARS}
    ports:
      - "{host_port}:{container_port}"
    networks:
      discovery-lab:
        ipv4_address: 172.30.0.{next_ip}
    mem_limit: {limit}
```

#### Type `tcpbanner` (OpenCanary)

Ajouter dans `docker/discovery-lab/opencanary/opencanary.conf` :

```json
"tcpbanner_{N}.enabled": true,
"tcpbanner_{N}.port": {port},
"tcpbanner_{N}.datareceivedbanner": "",
"tcpbanner_{N}.initbanner": "{banniere_exacte}",
"tcpbanner_{N}.alertstring.enabled": false,
"tcpbanner_{N}.alertstring": ""
```

ET mapper le port dans `docker-compose.yml` section opencanary.
Limite OpenCanary : 10 TCP banners max.

#### Type `http`

Utiliser un conteneur nginx/python avec config dediee pour les bannieres HTTP complexes.

**Demarrer et capturer la banniere reelle :**

```bash
cd docker/discovery-lab
./lab.sh stop && ./lab.sh start all

echo "" | timeout 3 nc -w2 127.0.0.1 {host_port} | head -1      # TCP
curl -sI http://127.0.0.1:{host_port} | head -10                  # HTTP
```

**EVALUATE ACT :**
- SUCCESS : service demarre + banniere capturee -> OBSERVE
- FAILURE : image absente ARM64 ou service en erreur -> REPLAN

---

## Phase OBSERVE

Verifier le pattern fingerprint correspondant :
```bash
ls data/fingerprints/*/{TAXONOMY}*.json data/fingerprints/*/NMAP_*{PRODUCT}*.json 2>/dev/null
```

Lancer scan LiaProbe :
```bash
curl -s -X POST http://localhost:8081/api/discovery/scan/start \
  -H "Content-Type: application/json" \
  -d '{"targets":["127.0.0.1"],"ports":"{host_port}","scan_mode":"thorough"}'
```

Attendre 15-30s, puis lire les logs fingerprinting :
```bash
psql_lia -c "SELECT timestamp, component, action, LEFT(message, 200) FROM unified_logs
      WHERE timestamp > NOW() - INTERVAL '2 minutes'
      AND component LIKE '%FINGER%'
      AND action NOT LIKE '%FAILED%'
      ORDER BY timestamp DESC LIMIT 10;"
```

---

## Phase EVALUATE

| Verdict | Condition | Decision |
|---------|-----------|----------|
| SUCCESS | taxonomy correcte + confidence >= 0.60 | ecrire preuve -> COMPLETE |
| PARTIAL | taxonomy correcte, pas de version | documenter dans notes -> COMPLETE |
| FAILURE | taxonomy incorrecte ou confidence < 0.60 | REPLAN |

---

## Phase REPLAN (sur chaque FAILURE)

**Alternative 1 :** Image Docker absente en ARM64
- Basculer vers type `tcpbanner` avec la meme banniere TCP
- Ou basculer vers type `http` si le service expose une interface web

**Alternative 2 :** Banniere TCP vide
- Tester en HTTP probe a la place
- Ajouter un delai de connexion dans la config

**Alternative 3 :** Pattern fingerprint absent
- Invoquer `/create-banner` pour creer le pattern (COUCHE 5 banner-server)
- Ou creer un pattern dans `data/fingerprints/lia/{TAXONOMY}.json`

**Apres 3 FAILURE consecutifs :** ESCALATE.

---

## Phase COMPLETE - Preuve de Recette (OBLIGATOIRE)

**INTERDICTION de passer a la technologie suivante sans avoir ecrit la preuve.**

Creer `docker/discovery-lab/recette/{TAXONOMY}_{PORT}.json` :

```json
{
  "technology": "Apache Tomcat",
  "taxonomy_code": "APACHE_TOMCAT",
  "port": 18888,
  "type": "docker",
  "image": "tomcat:10-jdk21",
  "ip_lab": "172.30.0.40",
  "date": "2026-03-01",
  "banner_expected": {
    "tcp": null,
    "http_headers": {"Server": "Apache-Coyote/1.1"},
    "http_body_contains": ["Apache Tomcat"],
    "http_title": null
  },
  "banner_received": {
    "tcp_raw": null,
    "http_headers": {"Server": "Apache-Coyote/1.1", "Content-Type": "text/html;charset=UTF-8"},
    "http_status": 200,
    "http_body_excerpt": "<html>...<h1>Apache Tomcat/10.1.34</h1>..."
  },
  "pattern_used": {
    "file": "data/fingerprints/nmap/NMAP_HTTP_APACHE_TOMCAT_COYOTE.json",
    "source": "nmap",
    "matchers_count": 5,
    "has_version_extract": true,
    "has_cpe": true
  },
  "scan_result": {
    "scan_id": 108,
    "taxonomy_detected": "NMAP_HTTP_APACHE_TOMCAT_COYOTE",
    "confidence": 0.85,
    "version_extracted": "10.1.34",
    "cpe_generated": "cpe:2.3:a:apache:tomcat:10.1.34:*:*:*:*:*:*:*",
    "scan_mode": "thorough",
    "duration_ms": 2340
  },
  "verdict": "PASS",
  "notes": "Detection correcte. Version extraite. CPE genere.",
  "commit": "abc123def"
}
```

Mettre a jour `docker/discovery-lab/recette/RECETTE_INDEX.md` :

```markdown
| # | Technologie | Port | Type | Pattern | Confidence | Version | Verdict | Date |
|---|------------|------|------|---------|------------|---------|---------|------|
| N | {Technology} | {port} | {type} | {pattern} | {conf} | {ver} | PASS | {date} |
```

---

## Ports et IPs lab

| Plage ports | Usage |
|-------------|-------|
| 10000-10999 | Services systeme (FTP, SSH, Nginx) |
| 11000-11999 | BDD, cache, middleware |
| 13000-13999 | Monitoring, management |
| 15000-15999 | Securite, auth, infra |
| 16000-17999 | Messaging, NoSQL |
| 18000-18999 | Applications web |
| 19000-19999 | APIs, search, monitoring |
| 20000-20999 | Agents, specialises |

| IPs | Usage |
|-----|-------|
| .10-.23 | Services reels |
| .30 | OpenCanary honeypot |
| .31-.33 | Honeypots |
| .40-.59 | Applications web |
| .60-.79 | Libre |

---

## RETEX (AFFICHE OBLIGATOIREMENT en fin de loop)

```
RETEX create-lab-banner {TECHNOLOGY} {DATE}
Iterations : {N}
Verdict final : SUCCESS / PARTIAL / FAILURE
Type service : docker / tcpbanner / http
Port : {PORT}
Banniere source : {source}
Confidence LiaProbe : {valeur}
Alternatives testees : {liste}
Preuve : docker/discovery-lab/recette/{TAXONOMY}_{PORT}.json
```

---

## Tracabilite (OBLIGATOIRE)

Creer `_alire/tracking/PLAN_LAB_BANNER_{TECH}_{YYYY-MM-DD}.md` au demarrage.

Logger dans `_alire/02_LOGS/Journals/decision_log.jsonl` :
```bash
echo '{"timestamp":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","session":"lab-banner-{TECH}","action":"ACTION","reasoning":"...","alternatives_rejected":["..."],"outcome":"SUCCESS|FAILURE","confidence":"high|medium|low","plan_ref":"PLAN_LAB_BANNER_{TECH}_{DATE}.md"}' >> _alire/02_LOGS/Journals/decision_log.jsonl
```

Apres completion :
- Mettre a jour `_alire/tracking/FINGERPRINTING_ENGINE_2026-02-28.md`
- Format journal : `- YYYY-MM-DD : **LIA patterns : {ancien} -> {nouveau}** (+{N} technos). Taxonomies : {LISTE}.`

---

## Campagne de recette systematique

```bash
./lab.sh start all
./lab.sh scan
./lab.sh recette   # liste ports, capture bannieres, scan LiaProbe, genere preuves JSON, RECETTE_INDEX.md
```

---

## Fichiers de reference

- Lab : `docker/discovery-lab/`
- Recettes : `docker/discovery-lab/recette/`
- Patterns : `data/fingerprints/{lia,nmap,recog,nuclei,wappalyzer}/`
- Skill COUCHE 5 : `.claude/skills/create-banner/SKILL.md`

*Skill v5.0 - 2026-04-04 - Agentic loop architecture*
