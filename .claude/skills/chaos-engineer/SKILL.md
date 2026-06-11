---
name: chaos-engineer
description: Resilience testing for LIA-SEC single-VPS topology -- design and execute controlled chaos experiments on backend Go (lia-backend systemd), PostgreSQL, nginx, Ollama, Worker API, n8n, LiaProbe agents. NO Litmus/Chaos Mesh (Kubernetes-only), NO Gremlin (commercial), NO production target without ROE. Use Pumba for Docker (n8n container), `tc netem` for network chaos, `stress-ng` for CPU/RAM, `kill -STOP` for process pause. Produces hypothesis -> blast radius decision -> safety rollback procedure -> game day runbook -> post-mortem template. Invoke before launching a resilience experiment, when planning a game day, when designing fault injection in CI, when testing auto-healing of `lia-backend`, when validating PostgreSQL backup restoration under failure.
license: MIT (upstream Jeffallan/claude-skills) -- adapted for LIA-SEC
allowed-tools: Read, Grep, Glob, Bash, Write, Edit
metadata:
  author: mo0ogly@proton.me
  upstream: https://github.com/Jeffallan/claude-skills/tree/main/skills/chaos-engineer
  version: "2.0.0-lia"
  domain: devops
  triggers: chaos engineering, resilience test, fault injection, kill backend, simulate outage, game day, blast radius, rollback test, auto-healing test, network chaos, latency injection, packet loss, OOM kill, disk full simulation, pumba, stress-ng, tc netem
  role: specialist
  scope: implementation
  output-format: experiment manifest + runbook + post-mortem template
  related-skills: devops-engineer, monitoring-expert, security-reviewer
  enforces-rules: R1, R6, R9, R10, R11, R14, R16
---

# Chaos Engineer (LIA-SEC adaptation)

> **CRITIQUE** : LIA-SEC est en SINGLE-VPS prod (`liascan.tech`). Pas de cluster, pas de blue-green, pas de Kubernetes. Toute experience chaos sur PROD = downtime utilisateur direct.
>
> **Regles ABSOLUES** :
> 1. **Premier passage : LOCAL** (`localhost:8081` dev, jamais `liascan.tech`)
> 2. **Si experience necessaire en prod** : ROE signee + window maintenance + maintainer present + rollback < 60s teste
> 3. **R14** : doc AVANT execution dans `vps_deployment_guide_user_en.md`
> 4. **Auto-healing existant** : `cron */5 min health check` deja en place. Verifier ce qu'il fait avant d'attaquer.

---

## 0. Failure modes connus LIA-SEC (ordonnes par criticite)

| # | Failure mode | Existant | Comportement attendu |
|---|--------------|----------|----------------------|
| 1 | `lia-backend` crash | systemd `Restart=on-failure RestartSec=5s` | Auto-restart < 10s, perte connexions in-flight |
| 2 | PostgreSQL down | aucun fallback | Backend retourne 500 sur tous endpoints DB |
| 3 | Disque plein `/opt/lia-sec/` | aucune alerte | Backup cron echoue silencieusement |
| 4 | OOM (32 GB RAM, 4 GB swap) | OOMKiller systemd | Backend tue, restart 5s |
| 5 | nginx down | aucun fallback | HTTPS down complet, monitoring externe ? |
| 6 | Ollama down | RAG fallback word-frequency | Embeddings degrades (deja teste lors RAG audit 2026-04-18) |
| 7 | n8n down | jobs CVE pipeline en pause | Reprise auto a restart |
| 8 | Network latency PostgreSQL | aucun timeout configure | Risque deadlock pool |
| 9 | LiaProbe agent disconnect | aucun re-enroll auto | Operateur doit reconnecter manuellement |
| 10 | Cert Let's Encrypt expire | renew auto certbot | Surveille via cron |

**A tester en priorite** : 1, 2, 3, 4, 8 (les plus impactants user).

---

## 1. Workflow agentique (6 phases)

```
[1] SYSTEM ANALYSIS
    - Cartographier dependances : nginx -> backend Go -> PostgreSQL + Ollama + n8n + Worker
    - Identifier critical paths : login (auth_jwt), CVE search (cve_search_api), AI analysis
    - Lister failure modes (cf section 0)
    - Verifier monitoring existant : Performance Monitoring API + unified_logs ERROR rate

[2] EXPERIMENT DESIGN
    - HYPOTHESIS : "Si je tue le backend, alors auto-restart < 10s, et perte de < N requetes en flight"
    - STEADY STATE : metric mesurable AVANT (ex: HTTP 200 rate > 99% sur /api/health pendant 5 min)
    - BLAST RADIUS : LOCAL only ? un seul service ? toutes les sessions interrompues ?
    - SAFETY :
        - Maintainer present
        - Rollback procedure ecrite + testee (< 60s)
        - Stop button (`./cleanup_services.sh both`)
        - Window maintenance (PROD : creneau 02h-04h ou ROE explicite)
    - Document dans `_alire/02_LOGS/Journals/chaos/YYYY-MM-DD_<exp>.md` AVANT execution

[3] EXECUTE
    - Local d'abord (`/opt/lia-sec/dev/`) -- toujours
    - Lancer monitoring continu en background (curl /api/health every 1s + log)
    - Injecter le fault (cf section 3 templates)
    - Observer : steady state casse-t-il ? Auto-healing fonctionne-t-il ? MTTR mesure ?
    - Rollback IMMEDIAT si steady state casse > seuil + alarme

[4] LEARN
    - Comparer attendu vs observe
    - Si surprise -> bug ou feature manquante (alerte, retry, circuit breaker)
    - Documenter findings dans `_alire/02_LOGS/Journals/chaos/<exp>_findings.md`
    - Ouvrir tickets pour fixes (priorite par criticite)

[5] AUTOMATE (futur)
    - Si experience repetable + value -> integrer dans CI weekly job
    - Pour LIA-SEC : envisager game day mensuel local + simulation prod en window 02h-04h annuelle

[6] POST-MORTEM
    - Template MTTR / impact / decision tree
    - RETEX dans `_alire/02_LOGS/Journals/retex/RETEX_CHAOS_*.md`
```

---

## 2. Reference Guide -- charger selon le contexte

| Topic | Reference | Charger quand |
|-------|-----------|---------------|
| Experiment design | `references/experiment-design.md` | Hypothesis, blast radius, rollback methodology |
| Infrastructure chaos | `references/infrastructure-chaos.md` | Server, network, zone failures (single-VPS adapter) |
| Game days | `references/game-days.md` | Planning + executing + learning |
| Tools | `references/chaos-tools.md` | **PRIORITAIRE** -- Pumba, stress-ng, tc netem, Chaos Toolkit |
| **NE PAS APPLIQUER** | `references/kubernetes-chaos.md` | LIA-SEC pas K8s |

---

## 3. Templates LIA-SEC

### 3.1 Outils LIA-SEC compatibles (no-Kubernetes)

| Outil | Type | Usage LIA-SEC |
|-------|------|---------------|
| `kill -STOP <pid>` / `kill -CONT <pid>` | Process pause | Simuler hang sans tuer (auto-restart NE se declenche pas) |
| `kill -9 <pid>` | Process crash | Tester `Restart=on-failure` systemd |
| `tc netem` | Network chaos | Latence/loss sur loopback ou interface |
| `stress-ng` | CPU/RAM stress | Tester degradation perf sous charge |
| `pumba` | Docker chaos | n8n container (ralentir, killer) |
| `iptables` | Network block | Bloquer port 5432 (PostgreSQL) ou 11434 (Ollama) |
| `dd if=/dev/zero of=/opt/lia-sec/dev/fill bs=1M count=N` | Disk fill | Simuler disque plein |

### 3.2 Experiment 1 : Backend crash + auto-restart

```bash
# Hypothesis : lia-backend kill -9 -> systemd restart < 10s, /api/health revient 200
# Steady state : /api/health 200 pendant 30s avant
# Blast radius : LOCAL only (pas en prod sans ROE)

# AVANT
sudo systemctl status lia-backend
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8081/api/health  # attendu 200

# Monitoring continu (background terminal)
while true; do
    code=$(curl -s -o /dev/null -m 2 -w "%{http_code}" http://localhost:8081/api/health)
    printf '%s code=%s\n' "$(date +%H:%M:%S.%3N)" "$code"
    sleep 1
done > /tmp/chaos_backend_health.log &
WATCH_PID=$!

# INJECT (LOCAL DEV uniquement)
PID=$(pgrep -f "/opt/lia-sec/dev/cmd/sigma_web/sigma_web_backend" | head -1)
echo "Killing PID $PID..."
sudo kill -9 "$PID"

# OBSERVE 30s
sleep 30
kill $WATCH_PID

# MEASURE
echo "Downtime / non-200 lines:"
grep -v "code=200" /tmp/chaos_backend_health.log

# CLEANUP
sudo systemctl status lia-backend  # doit etre running
```

**Attendu** : 5-10 sec de 000 / 502, puis retour 200. Si plus long -> bug systemd unit ou init backend.

### 3.3 Experiment 2 : PostgreSQL down

```bash
# Hypothesis : PostgreSQL stop -> backend retourne 500 sur DB endpoints, /api/health reste 200
# (parce que /api/health ne verifie PAS la DB connectivity actuellement -- a verifier)

# AVANT
curl -s http://localhost:8081/api/health
curl -s http://localhost:8081/api/cve/search?q=apache | head -c 200

# INJECT
sudo systemctl stop postgresql

# OBSERVE
curl -s -m 5 http://localhost:8081/api/health
curl -s -m 5 http://localhost:8081/api/cve/search?q=apache

# CLEANUP
sudo systemctl start postgresql
sleep 3
curl -s http://localhost:8081/api/cve/search?q=apache | head -c 200  # OK ?
```

**Findings attendus** : `/api/health` retourne probablement 200 meme PG down (false positive). Bug a fix : `/api/health` devrait inclure check DB.

### 3.4 Experiment 3 : Network latency PostgreSQL

```bash
# Hypothesis : 500ms latence sur 5432 -> requetes lentes mais pas de timeout
# Local DEV uniquement

# Add latency 500ms +/- 100ms on loopback to port 5432
sudo tc qdisc add dev lo root handle 1: prio
sudo tc qdisc add dev lo parent 1:3 handle 30: netem delay 500ms 100ms
sudo tc filter add dev lo protocol ip parent 1:0 prio 3 u32 \
    match ip dport 5432 0xffff flowid 1:3

# Observe (parralel terminal)
time curl -s http://localhost:8081/api/cve/search?q=apache > /dev/null

# CLEANUP (CRITIQUE -- sinon latence persistante)
sudo tc qdisc del dev lo root
```

### 3.5 Experiment 4 : Disk fill

```bash
# Hypothesis : /opt/lia-sec/ a 10% libre -> alerte Performance Monitoring + backup echoue
# LOCAL uniquement

# AVANT
df -h /opt/lia-sec/
du -sh /opt/lia-sec/dev/_alire/temp/

# INJECT (remplir 90% du disque restant)
FREE_KB=$(df -k /opt/lia-sec/ | tail -1 | awk '{print $4}')
FILL_KB=$((FREE_KB * 90 / 100))
dd if=/dev/zero of=/opt/lia-sec/dev/_alire/temp/CHAOS_FILL bs=1024 count=$FILL_KB

# OBSERVE
df -h /opt/lia-sec/
# Tester ecriture log : doit echouer
PGPASSWORD="$LIA_DB_PASS" psql ... -c "INSERT INTO unified_logs ..." # behavior?
# Tester backup : doit echouer
/opt/lia-sec/scripts/backup_postgres.sh  # doit fail proprement

# CLEANUP
rm -f /opt/lia-sec/dev/_alire/temp/CHAOS_FILL
df -h /opt/lia-sec/
```

### 3.6 Game day runbook template

```markdown
# Game Day : <experience> -- YYYY-MM-DD
## Participants
- Maintainer : mo0ogly@proton.me
- Observers : ...
## Window
- Debut : YYYY-MM-DD HH:MM TZ
- Fin attendue : HH:MM
- Window prod : OUI (autorise par ROE) | NON (LOCAL only)

## Pre-game
- [ ] Backup PostgreSQL frais : `/opt/lia-sec/scripts/backup_postgres.sh`
- [ ] `git status` clean, derniere version sur master
- [ ] Stop button teste : `./cleanup_services.sh both` reussit en < 30s
- [ ] Monitoring terminal lance (loop curl health)

## Experiments
1. Backend crash (cf section 3.2) -- attendu : 5-10s downtime
2. PostgreSQL stop (cf 3.3) -- attendu : 500 sur DB endpoints
3. ...

## Per-experiment template
- [ ] Steady state mesure
- [ ] Hypothesis ecrite
- [ ] Inject
- [ ] Observe (5-30s)
- [ ] Verdict : EXPECTED | SURPRISE
- [ ] Rollback verifie
- [ ] Findings notes

## Post-game
- [ ] Tous services UP : `systemctl status lia-backend nginx postgresql`
- [ ] Smoke test 5 endpoints critiques
- [ ] Rapport final dans `_alire/02_LOGS/Journals/chaos/YYYY-MM-DD_gameday.md`
- [ ] Tickets ouverts pour fixes identifies
```

### 3.7 Post-mortem template (apres incident reel ou chaos surprise)

```markdown
# Post-mortem : <incident> -- YYYY-MM-DD

## TL;DR (3 lignes)
...

## Timeline
- HH:MM:SS : detection
- HH:MM:SS : alerte recue
- HH:MM:SS : cause root identifiee
- HH:MM:SS : fix applique
- HH:MM:SS : retour a la normale

## Impact
- Utilisateurs affectes : ...
- Donnees perdues : ...
- SLO violated : ...

## Root cause
- 5 Whys
- Systemic vs human

## What went well
- ...

## What went wrong
- ...

## Action items (avec owner + due date)
- [ ] Fix : ... (owner: ..., due: YYYY-MM-DD)
- [ ] Monitoring gap : ...
- [ ] Runbook update : ...
- [ ] Game day a faire : ...

## Cross-references
- Experiment chaos : `_alire/02_LOGS/Journals/chaos/YYYY-MM-DD_*.md`
- Logs : `psql_lia -c "SELECT * FROM unified_logs WHERE timestamp BETWEEN ... AND ..."`
```

---

## 4. Anti-patterns interdits (refus immediat)

| INTERDIT | A la place |
|----------|-----------|
| Chaos sur `liascan.tech` PROD sans ROE signee + maintainer present | LOCAL `/opt/lia-sec/dev/` ou window 02-04h ROE |
| Pas de rollback procedure < 60s teste AVANT inject | Toujours tester rollback en LOCAL d'abord |
| Pas de monitoring continu pendant l'experience | curl loop ou Performance API obligatoire |
| Inject sur plusieurs failure modes simultanement | Un seul fault a la fois (sinon analyse impossible) |
| `tc qdisc` sans `tc qdisc del` final | Toujours cleanup -- sinon latence persistante |
| Disk fill sans `rm` final | Toujours cleanup |
| Ignorer auto-healing existant cron */5min | Verifier ce qu'il fait AVANT d'attaquer |
| Game day sans participants notifies | Notifier 24h+ avant + canal dedie |
| Skip post-mortem ("ca a marche, OK") | Toujours documenter findings (meme positifs) |
| Chaos en prod sans backup PostgreSQL recent | Backup obligatoire H-1 |
| Emojis dans runbook / post-mortem (R10) | `[OK]` / `[FAIL]` |

---

## 5. Output template

```markdown
# Chaos Experiment : <exp> -- YYYY-MM-DD
## Hypothesis
"Si <fault>, alors <expected behavior>, et <metric> reste dans <bound>"

## Steady state
- Metric : ...
- Mesure AVANT : ... (sample 30s+)

## Blast radius
- Cible : LOCAL `localhost:8081` | PROD `liascan.tech` (ROE jointe)
- Services impactes : ...
- Utilisateurs impactes : 0 (LOCAL) | N (PROD window)

## Safety controls
- Stop button : `./cleanup_services.sh both`
- Rollback teste en : N seconds
- Maintainer present : oui
- Backup frais : oui (HH:MM)

## Execution
1. Pre : ...
2. Inject : ...
3. Observe : ... (duration)
4. Cleanup : ...

## Results
- Hypothesis confirmed : OUI | NON
- Surprises : ...
- MTTR mesure : N seconds

## Action items
- [ ] Fix gap monitoring
- [ ] Doc runbook update
- [ ] Re-test dans X jours
```

---

## 6. Score agentique attendu (>= 40/50)

| Critere | Min | Comment l'atteindre |
|---------|-----|---------------------|
| C1 Decomposition | 8/10 | Workflow 6 phases respecte, un fault a la fois |
| C2 Planification (THINK) | 9/10 | Hypothesis + blast radius + rollback ECRITS AVANT inject |
| C3 Replanification | 8/10 | Si surprise -> stop, document, decide go/no-go pour suite |
| C4 Outillage | 8/10 | Outils no-K8s adaptes (tc netem, stress-ng, pumba) ; jamais Litmus/ChaosMesh |
| C5 Tracabilite | 8/10 | Plan + runbook + findings + post-mortem + Librarian Gate |
