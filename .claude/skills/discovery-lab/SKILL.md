---
name: discovery-lab
description: >
  Gestionnaire du lab de simulation Discovery pour LIA-Scan. Demarre, arrete, configure et
  scanne les services simules (Docker + OpenCanary + ContainerLab). Permet de tester le
  taxonomy_mapper et le moteur de fingerprinting sans reseau client reel.
user-invocable: true
argument-hint: "[start|stop|status|scan|config|add|remove]"
---

# Discovery Lab Skill - Gestionnaire de Lab de Simulation

Ce skill gere un environnement Docker compose de 3 couches de simulation :
1. **Vrais services Docker** (PostgreSQL, Redis, MongoDB, Nginx, OpenSSH, Jenkins, etc.)
2. **OpenCanary honeypot** (MSSQL, RDP, FTP, Telnet, VNC, bannieres Cisco/Juniper)
3. **ContainerLab** (FortiGate, Cisco IOS-XE - a venir, necessite images vendor)

## Emplacement

```
LAB_DIR = /home/mo0ogly/Bureau/vscode_lia_audit/docker/discovery-lab/
```

Structure :
```
docker/discovery-lab/
    docker-compose.yml       # Definition des services
    lab.sh                   # Script de gestion CLI
    opencanary/
        opencanary.conf      # Configuration du honeypot
    scan-results.txt         # Derniers resultats Nmap (genere)
    scan-results.xml         # Resultats XML (genere)
```

---

## COMMANDES

### `/discovery-lab start [service...]`

Demarrer le lab (tous les services ou une selection).

```bash
cd /home/mo0ogly/Bureau/vscode_lia_audit/docker/discovery-lab
./lab.sh start                          # Tous les services standards
./lab.sh start postgres redis openssh   # Selection
./lab.sh start-heavy                    # Inclut GitLab + Splunk (8+ GB RAM)
```

Apres demarrage, afficher le status et les IPs.

### `/discovery-lab stop`

```bash
./lab.sh stop
```

### `/discovery-lab status`

Afficher l'etat de chaque service, les IPs, et les ports.

```bash
./lab.sh status
./lab.sh ips
./lab.sh services
```

### `/discovery-lab scan`

Lancer un Nmap de validation pour verifier que les bannieres sont correctement detectees.

```bash
./lab.sh scan                # Scan rapide -sV
./lab.sh scan-full           # Scan complet -sV -sC -O
```

Apres le scan, analyser les resultats et les comparer avec les taxonomies attendues.

### `/discovery-lab config`

Modifier la configuration OpenCanary pour ajouter/changer des bannieres.

1. Lire le fichier `opencanary/opencanary.conf`
2. Modifier les bannieres selon le besoin (ex: changer `telnet.banner` pour simuler un PaloAlto)
3. Redemarrer OpenCanary : `docker compose restart opencanary`

### `/discovery-lab add <service>`

Ajouter un nouveau service au lab. Etapes :
1. Chercher l'image Docker officielle du service
2. Ajouter la section dans `docker-compose.yml` avec une IP dans 172.30.0.x
3. Mettre a jour `lab.sh cmd_ips()` et `cmd_services()`
4. Tester avec `./lab.sh start <service>` puis `./lab.sh scan`

### `/discovery-lab remove <service>`

Retirer un service du lab :
1. Supprimer la section du `docker-compose.yml`
2. Mettre a jour `lab.sh`
3. `docker compose down` pour nettoyer

---

## SERVICES DISPONIBLES

### Couche 1 : Vrais services Docker

| Service | IP | Port | Taxonomie LIA-Scan | Image Docker |
|---------|-----|------|-------------------|-------------|
| postgres | 172.30.0.10 | 5432 | POSTGRESQL | postgres:16-alpine |
| redis | 172.30.0.11 | 6379 | REDIS | redis:7-alpine |
| mongo | 172.30.0.12 | 27017 | MONGODB | mongo:7 |
| elasticsearch | 172.30.0.13 | 9200 | ELASTIC | elasticsearch:8.17.0 |
| nginx | 172.30.0.14 | 80 | web server | nginx:1.27-alpine |
| apache | 172.30.0.15 | 80 | APACHE | httpd:2.4 |
| openssh | 172.30.0.16 | 2222 | OPENSSH | linuxserver/openssh-server |
| jenkins | 172.30.0.17 | 8080 | JENKINS | jenkins/jenkins:lts-jdk21 |
| grafana | 172.30.0.18 | 3000 | GRAFANA | grafana/grafana |
| zabbix-server | 172.30.0.19 | 10051 | ZABBIX | zabbix-server-pgsql:7.0 |
| zabbix-agent | 172.30.0.20 | 10050 | ZABBIX | zabbix-agent:7.0 |
| gitlab (heavy) | 172.30.0.21 | 80 | GITLAB | gitlab-ce:latest |
| mysql | 172.30.0.22 | 3306 | MYSQL | mysql:8.0 |
| mariadb | 172.30.0.23 | 3306 | MARIADB | mariadb:11 |
| splunk (heavy) | 172.30.0.24 | 8089 | SPLUNK | splunk/splunk:latest |

### Couche 2 : OpenCanary (172.30.0.30)

| Service simule | Port | Banniere | Taxonomie |
|---------------|------|----------|-----------|
| MSSQL | 1433 | SQL Server 2019 TDS | MSSQL |
| RDP | 3389 | Remote Desktop | WINDOWS |
| FTP | 21 | ProFTPD 1.3.6 | FTP |
| Telnet | 23 | FortiGate-VM64 login | FORTIGATE |
| VNC | 5900 | VNC auth | VNC |
| TCP banner | 8444 | SSH-2.0-Cisco-1.25 | CISC |
| TCP banner | 8445 | SSH-2.0-JUNOS-13.3R6.5 | JUNI |

### Couche 3 : ContainerLab (a venir)

Necessite des images QEMU vendeur (FortiGate qcow2, Cisco CSR1000v).
Voir `_alire/research_discovery/discovery/investigated/2026-02-28_simulation-lab-options.md`

---

## RESEAU

- Subnet : `172.30.0.0/24`
- Gateway : `172.30.0.1`
- Driver : bridge (isole du host)
- Les ports sont aussi exposes sur le host (mapping 1xxxx:port)

## CREDENTIALS LAB

Tous les services utilisent les memes credentials de lab :
- User : `labuser`
- Password : `labpass123`
- Ces credentials sont UNIQUEMENT pour le lab, jamais en production.

---

## Decomposition des sous-taches

Au demarrage, identifier les sous-taches independantes avant toute action :

- [ ] Sous-tache 1 : verifier l'etat du lab (`docker compose ps`, IPs, services attendus)
- [ ] Sous-tache 2 : demarrer les services cibles (`./lab.sh start [service...]`)
- [ ] Sous-tache 3 : lancer le scan de validation (`./lab.sh scan` ou `scan-full`)
- [ ] Sous-tache 4 : analyser les resultats (bannieres detcetees vs taxonomies attendues)
- [ ] Sous-tache 5 : ajuster la configuration (OpenCanary, docker-compose.yml, lab.sh)
- [ ] Sous-tache 6 : sauvegarder les resultats dans `_alire/temp/discovery-lab/`

Les sous-taches 3 et 4 forment une boucle iterable. Les sous-taches 5 et 6 dependent de 4.
Utiliser `TaskCreate` pour tracker si > 3 services ajustes simultanement.

## Plan d'execution

Pour toute session de validation complete ou ajout de services :

1. Creer `_alire/tracking/PLAN_DISCOVERY_LAB_{FEATURE}_{YYYY-MM-DD}.md` avant de demarrer le lab.
2. Template : `_alire/tracking/PLAN_TEMPLATE.md`.
3. Cocher chaque sous-tache a la completion.
4. Si replanification : Status -> REPLANIFIE + lien vers nouveau plan.

Pour un ajout ponctuel (1 service, < 3 fichiers modifies) : plan inline suffit.

## Adaptation et replanification

Si 2 operations consecutives echouent (ex: service ne demarre pas + scan ne detecte pas la banniere) :

- STOP
- Invoquer `/replan` -> produit `PLAN_DISCOVERY_LAB_*_REPLAN_*.md`
- NE PAS improviser de contournement (ex: modifier l'IP a la volee sans plan)

Declencheurs typiques :
- Service refuse de demarrer apres 2 tentatives (image absente, port conflit) -> REPLAN
- Banniere detectee incorrectement apres modification OpenCanary -> REPLAN
- Scan retourne 0 services identifies sur un subnet attendu -> REPLAN

Escalade : si 3 replans sur la meme operation echouent -> STOP, escalader a l'utilisateur avec le diagnostic complet.

## Outils declares

| Outil | Usage | Retry policy |
|-------|-------|--------------|
| `Read`, `Glob` | Explorer docker-compose.yml, opencanary.conf, lab.sh | N/A |
| `Edit`, `Write` | Modifier docker-compose.yml, opencanary.conf, lab.sh | N/A |
| `Bash ./lab.sh start/stop/status/scan` | Gestion du lab (R9 equivalent Docker) | 1 retry ; echec -> diagnose logs |
| `Bash docker compose logs <service>` | Diagnostiquer un service qui ne demarre pas | N/A |
| `Bash nmap -sV <ip>` | Scan de validation manuel | 1 retry si timeout reseau |
| `TaskCreate` | Tracking si > 3 services ajustes en parallele | N/A |

Selection dynamique : `Edit` pour modification partielle de fichier existant. `Write` uniquement pour un nouveau fichier de configuration. `Bash docker compose logs` AVANT de modifier la config si un service ne demarre pas.

## TRACABILITE AGENTIQUE

### Decision log

**Logger dans `_alire/02_LOGS/Journals/decision_log.jsonl`** les operations significatives :
- Ajout/suppression de service (avec justification)
- Modification de banniere OpenCanary (avant/apres)
- Resultat de scan (services identifies vs attendus)
- Ecart taxonomie detecte (banniere vs mapping)

Format :
```json
{"timestamp":"...","session":"discovery-lab-{date}","action":"...","reasoning":"...","alternatives_rejected":["..."],"outcome":"...","confidence":"high","plan_ref":"PLAN_DISCOVERY_LAB_*.md"}
```

### Plan pour workflows de validation

**Pour les sessions de validation completes** (start -> scan -> ajust -> stop) :
```bash
# Fichier: _alire/tracking/PLAN_DISCOVERY_LAB_{YYYY-MM-DD}.md
```

Le plan trace : services testes, resultats scan, ecarts identifies, corrections appliquees.

RETEX en fin de session si score agentique < 40/50 -> `_alire/02_LOGS/Journals/retex/RETEX_DISCOVERY_LAB_YYYY-MM-DD.md`.

### Diagnostic d'erreurs

**Si un service ne demarre pas ou n'est pas detecte :**
1. Verifier les logs Docker : `docker compose logs <service>`
2. Verifier le port mapping : `docker compose ps`
3. Proposer alternatives (image differente, port different)
4. Si 2 tentatives echouent -> REPLAN (voir "Adaptation et replanification")

### Persistance des resultats

Les resultats de scan DOIVENT etre sauvegardes dans `_alire/temp/discovery-lab/` (pas seulement dans le repertoire du lab) pour tracabilite inter-sessions.

---

## WORKFLOW DE VALIDATION

```
1. /discovery-lab start          # Demarrer les services
2. /discovery-lab status         # Verifier que tout tourne
3. /discovery-lab scan           # Scanner avec Nmap
4. Analyser les resultats :
   - Chaque service doit etre correctement identifie par Nmap
   - Les bannieres doivent correspondre aux taxonomies attendues
5. Tester le taxonomy_mapper :
   - Passer les resultats du scan au taxonomy_mapper
   - Verifier que les codes taxonomie sont corrects
6. Ajuster si necessaire :
   - Modifier les regles du taxonomy_mapper
   - Modifier les bannieres OpenCanary
   - Ajouter des services manquants
7. /discovery-lab stop           # Arreter quand fini
```

---

## AJOUT DE SERVICES

Pour ajouter une nouvelle technologie au lab :

1. **Chercher l'image Docker** officielle sur Docker Hub
2. **Choisir une IP** dans la plage 172.30.0.25-29 (services) ou 172.30.0.31+ (honeypot)
3. **Ajouter au docker-compose.yml** en suivant le pattern existant
4. **Tester** : `./lab.sh start <service>` puis `nmap -sV 172.30.0.xx`
5. **Documenter** : mettre a jour les tableaux dans ce skill et dans lab.sh

---

## VERIFICATION GATE (BLOQUANT)

Avant de declarer une session de lab terminee, valider l'ensemble des points :

- [ ] Tous les services declares dans le PLAN sont demarres (`./lab.sh status` = UP)
- [ ] Le scan Nmap a identifie chaque service avec la taxonomie attendue (zero ecart non-documente)
- [ ] Aucune action sur une cible non autorisee (subnet 172.30.0.0/24 uniquement -- jamais le reseau client)
- [ ] Les resultats de scan sont sauvegardes dans `_alire/temp/discovery-lab/`
- [ ] Toute modification de configuration (OpenCanary, docker-compose) est committee ou documentee dans le plan

Un ecart taxonomie non resolu = session PARTIELLE, pas TERMINEE. Documenter dans le PLAN sous "Ecarts et replanification".

---

## Scoring agentique

| Critere | Score |
|---------|-------|
| C1 Decomposition : sous-taches identifiees avant demarrage du lab ? | /10 |
| C2 Planification : PLAN_DISCOVERY_LAB_*.md cree et suivi ? | /10 |
| C3 Replanification : /replan declenche sur 2+ echecs consecutifs (service / scan) ? | /10 |
| C4 Outillage : outils choisis dynamiquement (Edit vs Write, scan vs logs) + skills domaine invoques ? | /10 |
| C5 Tracabilite : decision_log alimente + resultats persistes + RETEX si score < 40 ? | /10 |

Score total /50 -- >= 40 : Exemplaire | 30-39 : Acceptable | < 30 : RETEX obligatoire
