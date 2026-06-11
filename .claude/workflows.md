# LIA-SEC Development Workflows

## Backend Go

```bash
# Build
cd /home/mo0ogly/Bureau/vscode_lia_audit/cmd/sigma_web && ./build_secure_lia.sh

# Run
./cleanup_services.sh backend

# Health Check
curl http://localhost:8081/api/health  # {"status":"ok", "database":"Connected", "version":"2.0.0"}

# Tests
go test -tags=unit ./...
cd /home/mo0ogly/Bureau/vscode_lia_audit/recette && ./run_recette.sh
```

Ajout nouveau fichier .go : Mettre a jour MANDATORY_FILES dans cleanup_services.sh

## Frontend React

```bash
cd /home/mo0ogly/Bureau/vscode_lia_audit/sigma-react-frontend
npm install && npm start    # Dev (localhost:3000)
npm run build               # Prod
npx tsc --noEmit            # Type check
cd ../recette/e2e && npm run test:headed  # E2E tests
```

Langue UI = TOUJOURS anglais (labels, boutons, messages, titres)

## Service Management

```bash
./cleanup_services.sh both      # Demarrer backend + frontend
./cleanup_services.sh backend   # Backend seul
./cleanup_services.sh status    # Verifier (ports + PIDs)
./cleanup_services.sh kill      # Arreter tout
```

INTERDIT : pkill -f sigma_web_backend / pkill -f "npm start" / lancement manuel

## Workflow developpement complet

```bash
./cleanup_services.sh kill                           # 1. Arreter
cd cmd/sigma_web && ./build_secure_lia.sh            # 2. Rebuild backend
cd sigma-react-frontend && npm run build             # 3. Rebuild frontend (si necessaire)
./cleanup_services.sh both                           # 4. Redemarrer
./cleanup_services.sh status                         # 5. Verifier
```

## Moteur LIA-Scan

```bash
ENGINE="/home/mo0ogly/Bureau/vscode_lia_audit/bin/lia_scan_engine"

# Build
./build_static_engine.sh

# Test mode MULTI
$ENGINE -multi -rules /path/to/rule_dir -events /path/to/test_data.json -quadrigramme TEST -date $(date +%Y%m%d)

# Production mode
$ENGINE --scan-taxonomy --taxonomy "ADDS" --branches "ADDS/SEC/GPO" --events events.json --rules lia_rules/rule_analysis --quadrigramme AD01 --date 20260109
```

## Database PostgreSQL

```bash
# Connection
psql -U lia_user -d lia_platform

# Backup/Restore
pg_dump -U lia_user -d lia_platform > backup_$(date +%Y%m%d).sql
psql -U lia_user -d lia_platform -f migration.sql
```

## Docker Services

| Service | Port | Start | Path |
|---------|------|-------|------|
| PostgreSQL | 5432 | `docker-compose up -d` | docker/postgres/ |
| Nmap | N/A | `docker-compose up -d` | docker/nmap/ |
| Zabbix | 8080 | `docker-compose up -d` | docker/zabbix/ |

## UI Development Workflow (3 etapes obligatoires)

1. **Backend API (Go):** Creer endpoint + logger
2. **Frontend UI (React):** Creer composant
3. **Test MCP (Playwright):** Simuler utilisateur reel

MCP Tools: browser_navigate, browser_snapshot, browser_click, browser_fill_form, browser_screenshot, browser_wait_for

## Package Management

TOUJOURS verifier derniere version AVANT installation :
- npm: `npm show <pkg> version` puis `npm install <pkg>@<ver>`
- Go: `go list -m -versions <mod>` puis `go get <mod>@<ver>`
- pip: `pip index versions <pkg>` puis `pip install --upgrade <pkg>`

INTERDIT : Installer sans verifier version, utiliser versions obsoletes (> 2 ans)

## Health Checks

```bash
curl http://localhost:8081/api/health              # Backend
psql -U lia_user -d lia_platform -c "SELECT version();"  # PostgreSQL
curl http://localhost:3000                          # Frontend
$ENGINE -version                                    # Moteur
```

## Troubleshooting

```bash
lsof -i :8081 && lsof -i :3000    # Port conflicts
./cleanup_services.sh kill          # Clean kill
./cleanup_services.sh both          # Restart clean
tail -f log/backend.log             # Backend logs
```
