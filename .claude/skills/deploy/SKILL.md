---
name: deploy
description: Pipeline complet dev -> git -> VPS production (liascan.tech). Deploiement, verification securite, react-doctor, health check, rollback. Utiliser quand on demande de deployer, pousser en prod, ou verifier l'etat du VPS.
metadata:
  user_invocable: "true"
  argument_hint: "[mode] (all|backend|frontend|sync|push|propagate|mirror|status|logs|check|full)"
---

> **PREMIERE ACTION OBLIGATOIRE :** Annoncer "Using deploy skill. Checking pre-deploy requirements..." comme premiere ligne de reponse.

# LIA-SEC Deployment Skill

Pipeline de deploiement dev local -> GitHub -> VPS production (liascan.tech).

## TRACABILITE AGENTIQUE (OBLIGATOIRE)

### Plan persistant
Creer `_alire/tracking/PLAN_DEPLOY_{MODE}_{YYYY-MM-DD}.md` (template: `_alire/tracking/PLAN_TEMPLATE.md`).

### Decision log
Logger dans `_alire/02_LOGS/Journals/decision_log.jsonl` les decisions non-triviales.
Format: `{"timestamp","session","action","reasoning","alternatives_rejected":[],"outcome","confidence","plan_ref"}`

### Replanification
Si 2 etapes echouent consecutivement → INVOQUER `/replan`.

### Scoring agentique (/50)
En fin de workflow, scorer sur : Decomposition, Planification, Replanification, Outillage dynamique, Tracabilite.

---

## Arguments

- `$ARGUMENTS[0]` - Mode de deploiement (optionnel, defaut: `all`)

| Mode | Description |
|------|-------------|
| `all` | Sync + build backend + build frontend + health check |
| `backend` | Sync + build backend uniquement |
| `frontend` | Sync + build frontend uniquement |
| `sync` | Rsync fichiers sans build |
| `push` | Git push + propagation auto VPS/dev |
| `propagate` | Git fetch+reset VPS/dev (sans push) |
| `mirror` | Mirror COMPLET disaster recovery (avec .git, .claude/) |
| `status` | Statut services VPS |
| `logs` | Derniers logs backend VPS |
| `check` | Pre-deploy checks uniquement (build, react-doctor, securite) |
| `full` | Check complet + commit + push + deploy all + verification |

---

## ARCHITECTURE VPS

```
VPS: 187.124.39.123 (liascan.tech)
OS: Ubuntu 24.04 x86_64, 8 vCPU, 32 Go RAM

/opt/lia-sec/
  source/      <- PRODUCTION (deploy.sh all/backend/frontend/sync)
  dev/         <- MIRROR DEV (deploy.sh mirror/propagate/push)

Services:
  lia-backend     :8081  (Go, systemctl restart lia-backend)
  nginx           :443   (HTTPS, Let's Encrypt)
  postgresql      :5432  (PostgreSQL 17)
  lia-worker-api  :9999  (Python worker)
  ollama          :11434 (AI, CPU only)
  n8n             :5678  (Docker)
```

---

## PIPELINE COMPLET (mode `full`)

### Phase 1 : Pre-deploy checks (BLOQUANT)

Executer dans cet ordre. Tout echec = STOP.

#### 1.1 Build TypeScript (zero erreur)

```bash
cd sigma-react-frontend
npm run build 2>&1
```

**Critere :** Exit code 0, zero erreur TypeScript. Les warnings Vite sont OK.

#### 1.2 React Doctor (score minimum 90/100)

```bash
cd sigma-react-frontend
npm run doctor 2>&1
```

**Critere :** Score >= 90/100. Warnings acceptables tant que le score est au-dessus du seuil.
**Lire le rapport :** noter les warnings `prefer-useReducer`, `no-giant-component`, etc.
Si score < 90, analyser les regressions AVANT de deployer.

#### 1.3 Security checks (non-bloquant mais rapporte)

```bash
# Hook securite (si gosec/semgrep installes)
.claude/hooks/security_check.sh
cat .claude/hooks/security.log 2>/dev/null | tail -20
```

**Critere :** Rapporter les findings HIGH/CRITICAL. Non-bloquant mais doit etre visible.

#### 1.4 Go build local (verification syntaxe)

```bash
cd /home/mo0ogly/Bureau/vscode_lia_audit
go build -mod=mod ./cmd/sigma_web/ 2>&1
```

**ATTENTION ARCHITECTURE :** Le binaire local (ARM64 Snapdragon X Elite) ne tourne PAS sur le VPS (x86_64).
Ce build sert uniquement a verifier la compilation. Le vrai build se fait SUR le VPS.

#### 1.5 Git status propre

```bash
git status
git diff --stat
```

**Critere :** Working tree clean OU changements commites. Pas de fichiers non trackes importants.

### Phase 2 : Commit et push

```bash
# Commit si necessaire (conventional commits obligatoire)
git add <fichiers specifiques>
git commit -m "feat|fix|docs|refactor(scope): description"

# Push vers GitHub
git push origin master
```

**REGLES GIT :**
- Conventional Commits obligatoire
- JAMAIS `git add .` ou `git add -A` (risque secrets)
- JAMAIS `--no-verify` (hooks = protection)
- JAMAIS `push --force` sans accord utilisateur
- JAMAIS "Co-Authored-By: Claude" dans les commits

### Phase 3 : Deploiement VPS

```bash
./deploy.sh all          # Ou backend/frontend selon besoin
```

**Ce que fait `deploy.sh` :**

1. **SSH check** - Verification connectivite VPS
2. **rsync** - Sync fichiers (exclut node_modules, .git, bin/, docker/, collect/)
3. **Build backend** - `go build` SUR le VPS (x86_64 natif), rollback auto si echec
4. **Build frontend** - `npm install + vite build` SUR le VPS
5. **Health check** - Services, HTTPS, certificat TLS, ressources

**Rollback automatique :** Si le backend ne demarre pas apres build, `deploy.sh` restaure `sigma_web_backend.prev`.

### Phase 4 : Verification post-deploy (OBLIGATOIRE)

#### 4.1 Health check services

```bash
./deploy.sh status
```

Verifier : Backend active, Nginx active, PostgreSQL active, HTTPS 200.

#### 4.2 Test API (depuis local)

```bash
# Health endpoint
curl -sf https://liascan.tech/api/health | jq .

# Login test
curl -sf -X POST https://liascan.tech/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"***"}' | jq .status
```

#### 4.3 Verification CORS

```bash
curl -sf -I -X OPTIONS https://liascan.tech/api/health \
  -H "Origin: https://liascan.tech" \
  -H "Access-Control-Request-Method: GET" 2>&1 | grep -i "access-control"
```

**CORS piege connu :** La variable `FRONTEND_URL` dans PostgreSQL (`system_variables`) controle l'origin CORS.
Si les requetes browser sont bloquees :
```sql
-- Sur le VPS
UPDATE system_variables SET value = 'https://liascan.tech' WHERE key = 'FRONTEND_URL';
-- Puis restart backend
systemctl restart lia-backend
```

#### 4.4 Verification logs VPS

```bash
./deploy.sh logs
```

Chercher : erreurs de demarrage, panics Go, erreurs SQL migration.

---

## GOTCHAS CONNUS

| Piege | Symptome | Solution |
|-------|----------|----------|
| **Binary ARM64 sur VPS x86_64** | `exec format error`, exit 203 | Build SUR le VPS (`deploy.sh` le fait), JAMAIS rsync le binaire local |
| **FRONTEND_URL = localhost** | CORS bloque toutes requetes browser | `UPDATE system_variables SET value='https://liascan.tech' WHERE key='FRONTEND_URL'` + restart |
| **Hardcoded localhost:8081** | API calls echouent en prod | Utiliser `ConfigurationService` + `import.meta.env.PROD` detection |
| **Backend init 30s** | 502 Bad Gateway temporaire | Attendre ~30s apres restart (560+ routes a charger) |
| **Auth header manquant** | 401 sur tous les endpoints | `fetchWithConfig` injecte auto le JWT depuis localStorage |
| **build_secure_lia.sh** | Fichiers Go manquants au build | Seul script de build autorise (liste explicite de fichiers .go) |
| **Pre-commit hook file size** | Commit bloque (800 lignes Go max) | Ajouter `// @allow-long-file` en premiere ligne du fichier |
| **SSH key GitHub** | `Permission denied (publickey)` | `gh auth setup-git` puis push HTTPS, ou ajouter cle a GitHub |
| **SQL migration partielle** | Table existe avec schema different | DROP CASCADE les tables, re-executer migration |
| **npm --legacy-peer-deps** | Conflits dependencies React 19 | Toujours utiliser `--legacy-peer-deps` pour npm install |

---

## MODES SPECIFIQUES

### Mode `push` (dev quotidien)

Pipeline le plus frequent. Push local -> GitHub -> VPS/dev auto.

```bash
./deploy.sh push
```

Fait : `git push origin master` + SSH VPS + `git fetch + reset --hard origin/master` dans `/opt/lia-sec/dev/`.
**Pre-requis :** Commits locaux propres, remote configure.

### Mode `propagate` (sans push)

Quand le push est deja fait (ou fait manuellement) :

```bash
./deploy.sh propagate
```

Fait : SSH VPS + `git fetch + reset --hard origin/master` dans `/opt/lia-sec/dev/`.

### Mode `mirror` (disaster recovery)

Replique l'environnement dev complet sur le VPS pour continuer a coder si le PC tombe.

```bash
./deploy.sh mirror
```

Fait :
- rsync projet COMPLET (avec .git) vers `/opt/lia-sec/dev/`
- Sync `~/.claude/` vers VPS
- Configure aliases `cc`/`ccc` pour Claude Code
- Verifie Go, Node, Git sur le VPS

**Pour dev depuis le VPS :** `ssh root@187.124.39.123` -> `liadev` -> `claude`

---

## COMMANDES RAPIDES

```bash
# Verifier l'etat sans rien deployer
./deploy.sh status

# Voir les logs backend
./deploy.sh logs

# Deploy rapide backend apres fix Go
./deploy.sh backend

# Deploy rapide frontend apres fix React
./deploy.sh frontend

# Pipeline complet quotidien
./deploy.sh push && ./deploy.sh all

# Apres compression contexte, verifier l'etat
./deploy.sh status
```

---

## CHECKLIST PRE-DEPLOY RAPIDE

1. [ ] `npm run build` dans sigma-react-frontend (zero erreur)
2. [ ] `npm run doctor` score >= 90
3. [ ] `go build -mod=mod ./cmd/sigma_web/` (compile OK)
4. [ ] `git status` propre (tout commite)
5. [ ] `git push origin master` (ou `./deploy.sh push`)
6. [ ] `./deploy.sh all` (ou backend/frontend)
7. [ ] `./deploy.sh status` (tout actif)
8. [ ] Test HTTPS `curl https://liascan.tech/api/health`
9. [ ] Test login si auth modifie

---

## ACCES VPS DIRECT (urgence uniquement)

```bash
ssh root@187.124.39.123

# Logs en temps reel
journalctl -u lia-backend -f

# Restart services
systemctl restart lia-backend
systemctl restart nginx

# PostgreSQL
sudo -u postgres psql -d lia_scan

# Verifier CORS
psql -U lia_admin -d lia_scan -c "SELECT * FROM system_variables WHERE key = 'FRONTEND_URL';"
```

**REGLE R11 :** JAMAIS modifier le code directement sur le VPS. Dev en local, deploy via `./deploy.sh`.
