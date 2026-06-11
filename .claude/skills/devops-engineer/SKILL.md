---
name: devops-engineer
description: DevOps for LIA-SEC stack -- Go backend deploy via systemd, React build + nginx + rsync, PostgreSQL backups + restore, GitHub Actions CI, single-VPS topology (liascan.tech), no Kubernetes / no Terraform / no AWS. Adapte le workflow LIA-SEC : `deploy.sh` (mirror/sync/build/health-check + auto-rollback), `cleanup_services.sh` (R9 single backend instance, R16), `build_secure_lia.sh` (whitelist Go), `lia-backend.service` (systemd), nginx /etc/nginx/sites-enabled, fail2ban, ufw, Let's Encrypt, cron backup PostgreSQL 2h AM. Invoke pour modifier deploy.sh, ajouter une etape CI, configurer un nouveau service systemd, durcir nginx, automatiser un backup, ecrire un runbook incident, debug deploy en prod.
license: MIT (upstream Jeffallan/claude-skills) -- adapted for LIA-SEC
allowed-tools: Read, Grep, Glob, Bash, Write, Edit
metadata:
  author: mo0ogly@proton.me
  upstream: https://github.com/Jeffallan/claude-skills/tree/main/skills/devops-engineer
  version: "2.0.0-lia"
  domain: devops
  triggers: deploy.sh, deploy script, systemd, lia-backend, nginx config, build_secure_lia, cleanup_services, GitHub Actions, CI/CD, backup PostgreSQL, restore PostgreSQL, fail2ban, ufw, Let's Encrypt, certbot, runbook, incident, MTTR, rollback, deployment strategy, blue-green, canary, healthcheck, auto-restart
  role: engineer
  scope: implementation
  output-format: code (bash + systemd + nginx + yaml CI)
  related-skills: deploy, monitoring-expert, security-reviewer, golang-pro
  enforces-rules: R1, R6, R8, R9, R10, R11, R14, R16
---

# DevOps Engineer (LIA-SEC adaptation)

> **Stack reel LIA-SEC** : Ubuntu 24.04, Go 1.25.1 backend (systemd `lia-backend`),
> React 19 frontend (build + rsync + nginx), PostgreSQL 17 (postgresql.service),
> nginx HTTPS (Let's Encrypt cert auto-renew), n8n (Docker compose), Worker API,
> Ollama. **Single VPS** : liascan.tech (187.124.39.123). **Pas de** Kubernetes,
> Terraform, AWS, GCP, Helm, ArgoCD.
>
> **Toujours** appliquer R14 : documenter toute modif infra dans
> `_alire/01_DOCUMENTATION/user-guides/vps_deployment_guide_user_en.md` AVANT
> de l'executer. Pas de commande sudo dans le chat sans entree dans le guide.

---

## 0. Topologie LIA-SEC (resume)

| Composant | Port | Service | Path |
|-----------|------|---------|------|
| Go backend | 8081 | `systemctl restart lia-backend` | `/opt/lia-sec/source/cmd/sigma_web/sigma_web_backend` |
| nginx HTTPS | 443 | `systemctl restart nginx` | `/etc/nginx/sites-enabled/` |
| PostgreSQL 17 | 5432 | `systemctl restart postgresql` | `/var/lib/postgresql/17/main/` |
| n8n | 5678 | Docker compose | `/opt/lia-sec/n8n/docker-compose.yml` |
| Worker API | 9999 | `systemctl restart lia-worker-api` | (Python n8n bridge) |
| Ollama | 11434 | `systemctl restart ollama` | `/usr/local/bin/ollama` |
| LiaProbe agent (port 8082 dev) | 8082 | `systemctl restart lia-liaprobe` | `/opt/lia-sec/liaprobe/` |

| Repertoire | Role |
|------------|------|
| `/opt/lia-sec/source/` | **PROD** -- code servi par nginx + backend systemd |
| `/opt/lia-sec/dev/` | **DEV MIRROR** -- copie pour dev avec Claude Code |
| `/opt/lia-sec/backups/` | Backups PostgreSQL auto (cron 2h AM, 7j retention) |
| `/etc/systemd/system/lia-*.service` | Units systemd |
| `/etc/nginx/sites-enabled/lia-sec` | Config nginx |
| `/etc/letsencrypt/live/liascan.tech/` | Certificat HTTPS |

---

## 1. Workflow agentique (6 phases)

```
[1] ASSESS
    - Quel composant a modifier ? (backend, frontend, nginx, systemd, cron, backup)
    - Impact prod ? Coupure attendue ? Window maintenance ?
    - Rollback prevu ? `git revert` + `deploy.sh backend` ou snapshot DB ?

[2] DESIGN
    - Document l'action dans `vps_deployment_guide_user_en.md` AVANT execution (R14)
    - Lister chaque commande sudo + verification post-action
    - Identifier les hooks (security_check.sh, check_build_list.sh, check_migration.sh)

[3] IMPLEMENT
    - Modifier deploy.sh / Dockerfile / systemd unit / nginx conf / cron
    - Tester en local AVANT push (`./deploy.sh status`, `nginx -t`, `systemd-analyze verify`)
    - Build whitelist Go : `./build_secure_lia.sh` (jamais `go build ./...`)

[4] VALIDATE
    - `./deploy.sh status` -> tous services UP
    - `curl https://liascan.tech/api/health` -> 200
    - `curl https://liascan.tech/api/diagnostic/build-info` -> commit_hash matches
    - Smoke test 1-2 endpoints critiques

[5] DEPLOY
    - `./deploy.sh push` -> git push + propagation auto VPS/dev
    - `./deploy.sh backend` (sync + build + restart + healthcheck + auto-rollback)
    - `./deploy.sh frontend` (build + rsync + nginx reload)
    - Surveiller `journalctl -u lia-backend -f` et nginx error log 30 sec post-deploy

[6] MONITOR
    - Alertes Performance Monitoring (existant : performance_api.go)
    - LogSystemEvent ERROR > seuil ?
    - Health check auto-healing cron */5 min (existant)
    - Si echec -> `journalctl --since "5 min ago" -u lia-backend` + `psql_lia -c "SELECT * FROM unified_logs WHERE level='ERROR' ORDER BY timestamp DESC LIMIT 20"`
```

---

## 2. Reference Guide -- charger selon le contexte

| Topic | Reference | Charger quand |
|-------|-----------|---------------|
| GitHub Actions | `references/github-actions.md` | Setup CI build/test/deploy automatique |
| Docker | `references/docker-patterns.md` | n8n Docker compose, LiaProbe Docker, banner-server lab |
| Deployment strategies | `references/deployment-strategies.md` | Blue-green, canary, rolling -- evaluer faisabilite single-VPS |
| Release automation | `references/release-automation.md` | Tag versioning, changelog, artifact retention |
| Incident response | `references/incident-response.md` | Runbook outage backend/PostgreSQL/nginx |
| Platform engineering | `references/platform-engineering.md` | Self-service tooling (cc.sh menu interactif existant) |
| **NE PAS APPLIQUER** | `references/kubernetes.md` | LIA-SEC n'est pas K8s |
| **NE PAS APPLIQUER** | `references/terraform-iac.md` | LIA-SEC n'utilise pas Terraform |

---

## 3. Templates LIA-SEC

### 3.1 Pattern systemd unit (lia-* services)

```ini
# /etc/systemd/system/lia-myservice.service
[Unit]
Description=LIA-SEC My Service
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=lia
WorkingDirectory=/opt/lia-sec/source/cmd/myservice
ExecStart=/opt/lia-sec/source/cmd/myservice/myservice_bin
Restart=on-failure
RestartSec=5
Environment=DATABASE_URL=postgresql://lia_admin:${LIA_DB_PASS}@localhost:5432/lia_scan?sslmode=disable
Environment=LIA_LOG_LEVEL=INFO
StandardOutput=journal
StandardError=journal

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/opt/lia-sec/source /var/log/lia-sec

[Install]
WantedBy=multi-user.target
```

### 3.2 Pattern nginx LIA-SEC (existant a etendre)

```nginx
# /etc/nginx/sites-enabled/lia-sec
server {
    listen 443 ssl http2;
    server_name liascan.tech;

    ssl_certificate     /etc/letsencrypt/live/liascan.tech/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/liascan.tech/privkey.pem;

    # Rate limiting (per IP)
    limit_req_zone $binary_remote_addr zone=api_limit:10m rate=30r/s;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'" always;

    # Frontend (React build)
    root /opt/lia-sec/source/sigma-react-frontend/build;
    index index.html;

    # Backend API proxy
    location /api/ {
        limit_req zone=api_limit burst=50 nodelay;
        proxy_pass http://localhost:8081;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
    }

    # SPA fallback
    location / {
        try_files $uri $uri/ /index.html;
    }
}

server {
    listen 80;
    server_name liascan.tech;
    return 301 https://$server_name$request_uri;
}
```

Toujours `nginx -t` avant `systemctl reload nginx`.

### 3.3 Pattern GitHub Actions (LIA-SEC compat)

```yaml
# .github/workflows/ci.yml
name: LIA-SEC CI
on:
  push:
    branches: [master]
  pull_request:
    branches: [master]
jobs:
  lint-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-go@v5
        with: { go-version: '1.25.1' }
      - name: govulncheck
        run: |
          go install golang.org/x/vuln/cmd/govulncheck@latest
          cd cmd/sigma_web && govulncheck -mode source ./...
      - name: gosec
        run: |
          go install github.com/securego/gosec/v2/cmd/gosec@latest
          cd cmd/sigma_web && gosec -quiet -exclude=G104,G107 ./...
      - name: Build whitelist Go
        run: bash cmd/sigma_web/build_secure_lia.sh
      - uses: actions/setup-node@v4
        with: { node-version: '22' }
      - name: React lint + build
        run: |
          cd sigma-react-frontend
          npm ci --no-audit --no-fund
          npm run lint
          npm run build

  # Pas de deploy auto. Deploy reste manuel via deploy.sh par maintainer.
```

### 3.4 Pattern backup PostgreSQL (cron, existant a referencer)

```bash
#!/usr/bin/env bash
# /opt/lia-sec/scripts/backup_postgres.sh
# Cron : 0 2 * * * /opt/lia-sec/scripts/backup_postgres.sh

set -e
BACKUP_DIR=/opt/lia-sec/backups
RETENTION_DAYS=7
DATE=$(date +%Y%m%d_%H%M%S)
LIA_DB_USER="${LIA_DB_USER:-lia_admin}"
LIA_DB_NAME="${LIA_DB_NAME:-lia_scan}"

mkdir -p "$BACKUP_DIR"

# Custom format dump (compressed, restorable selectively)
PGPASSWORD="$LIA_DB_PASS" pg_dump \
    -h localhost -U "$LIA_DB_USER" -d "$LIA_DB_NAME" \
    -F c -f "$BACKUP_DIR/lia_scan_${DATE}.dump"

# Verify dump integrity
PGPASSWORD="$LIA_DB_PASS" pg_restore -l "$BACKUP_DIR/lia_scan_${DATE}.dump" >/dev/null

# Retention
find "$BACKUP_DIR" -name "lia_scan_*.dump" -mtime +$RETENTION_DAYS -delete

# Log to unified_logs
PGPASSWORD="$LIA_DB_PASS" psql -h localhost -U "$LIA_DB_USER" -d "$LIA_DB_NAME" -c \
    "INSERT INTO unified_logs (level, component, action, message) VALUES \
    ('INFO', 'BACKUP', 'COMPLETED', 'Backup ${DATE} created, retention ${RETENTION_DAYS}d')" >/dev/null
```

### 3.5 Pattern restore PostgreSQL (DR)

```bash
# 1. Verifier le dump avant restore
pg_restore -l /opt/lia-sec/backups/lia_scan_YYYYMMDD_HHMMSS.dump | head -20

# 2. Stop le backend pour eviter writes pendant restore
sudo systemctl stop lia-backend

# 3. Restore (ATTENTION: drop avant si full restore)
PGPASSWORD="$LIA_DB_PASS" pg_restore \
    -h localhost -U lia_admin -d lia_scan \
    --clean --if-exists --no-owner \
    /opt/lia-sec/backups/lia_scan_YYYYMMDD_HHMMSS.dump

# 4. Restart backend
sudo systemctl start lia-backend

# 5. Health check
sleep 5 && curl -sf http://localhost:8081/api/health
```

### 3.6 Pattern incident runbook (template)

```markdown
# Runbook : <Incident type> -- LIA-SEC

## Symptoms
- ...

## Diagnostic (en parallele si possible)
1. `systemctl status lia-backend` -- service up ?
2. `curl -sf http://localhost:8081/api/health` -- backend repond ?
3. `journalctl -u lia-backend --since "10 min ago" | grep -i error`
4. `psql_lia -c "SELECT * FROM unified_logs WHERE level IN ('ERROR','CRITICAL') AND timestamp > NOW() - INTERVAL '10 min' ORDER BY timestamp DESC LIMIT 30"`
5. `df -h /opt/lia-sec` -- disque ?
6. `free -h` -- RAM ?
7. `pg_stat_activity` orphans : `psql_lia -c "SELECT pid, state, query FROM pg_stat_activity WHERE state != 'idle'"`

## Mitigation
- ...

## Validation post-fix
- ...

## Escalation
- Maintainer : mo0ogly@proton.me
```

---

## 4. Anti-patterns interdits (refus immediat)

| INTERDIT | A la place |
|----------|-----------|
| Modif `/etc/` ou cron sans documenter dans `vps_deployment_guide_user_en.md` AVANT (R14) | Doc d'abord, exec ensuite |
| `kubectl ...` / `helm ...` / `terraform ...` | LIA-SEC = single VPS, pas de K8s/Terraform |
| `go build ./...` ou `go test ./...` | `./build_secure_lia.sh` (whitelist) (R16, cmd/sigma_web/CLAUDE.md) |
| `pkill sigma_web_backend` | `./cleanup_services.sh kill\|both\|backend` (R9) |
| Lancer une 2eme instance backend en parallele (cleanup + nohup) | R16 -- tjrs `cleanup_services.sh kill` AVANT start |
| `sudo systemctl restart lia-backend && systemctl restart lia-backend` (sans wait) | wait health check entre commandes |
| Push to remote sans `./deploy.sh status` OK | Toujours valider local avant push |
| `git push --force` sur `master` | Jamais (R1) |
| `npm audit fix --force` | Lister vulns + accord user (R1) |
| Skip hooks pre-commit (`--no-verify`) | Fix the underlying issue |
| Modifier directement `/opt/lia-sec/source/` (prod) sans deploy.sh | R11 -- toujours dev local + deploy.sh |
| Backup non chiffre / restore sans dry-run | `pg_restore -l` d'abord ; chiffrement au repos pour cle export |
| `latest` tag Docker en prod | Pinned version explicite |
| Emojis dans systemd / nginx / runbook | (R10) |

---

## 5. Output template

```markdown
# DevOps Change : <description> -- YYYY-MM-DD

## 1. Contexte
- Service touche : ...
- Impact prod : ...
- Window maintenance : ...
- Rollback procedure : ...

## 2. Documentation pre-action (R14)
- Section ajoutee dans `vps_deployment_guide_user_en.md` :
  - Date : YYYY-MM-DD
  - Commandes : ...
  - Verification : ...

## 3. Implementation
- Fichiers modifies : `deploy.sh`, `/etc/systemd/system/lia-xxx.service`, ...
- Tests locaux : `nginx -t`, `systemd-analyze verify`, `./deploy.sh status`

## 4. Validation
- `curl /api/health` : 200
- `journalctl -u lia-backend --since "5 min ago"` : 0 ERROR
- Smoke test : ...

## 5. Rollback (si necessaire)
```bash
git revert <SHA>
./deploy.sh backend
sudo systemctl restart lia-backend
```

## 6. Monitor (24h post-deploy)
- Performance Monitoring API (existant) : OK
- ERROR rate stable
```

---

## 6. Score agentique attendu (>= 40/50)

| Critere | Min | Comment l'atteindre |
|---------|-----|---------------------|
| C1 Decomposition | 8/10 | Workflow 6 phases respecte |
| C2 Planification (THINK) | 9/10 | R14 doc AVANT execution + 2+ alternatives (rollback methods) |
| C3 Replanification | 8/10 | REPLAN sur health check KO + alternatives (rollback git, restore DB, restart sequence) |
| C4 Outillage | 8/10 | nginx -t + systemd-analyze + deploy.sh status AVANT prod |
| C5 Tracabilite | 8/10 | Plan + RETEX + commit unique avec runbook + Librarian Gate |
