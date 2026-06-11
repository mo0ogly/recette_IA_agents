---
name: monitoring-expert
description: Observability + perf testing pour LIA-SEC -- structured logging via `LogSystemEvent` + `unified_logs` PostgreSQL (existant), Performance Monitoring API existante (17 endpoints, snapshots 5min), AI metrics (`ai_realtime_stats_api.go`), security audit events. Etend l'existant avec : Prometheus exporter (futur), Grafana dashboards (RED/USE method), alertes seuils, k6/Artillery load tests sur endpoints critiques (CVE search, AI Analysis, Discovery scan). PAS de Pino/Winston (Go LogSystemEvent only), PAS d'OpenTelemetry instrumentation tracing-distribue (single-VPS, non requis). Invoke pour ajouter une metric, definir un seuil d'alerte, profiler un endpoint lent, planifier capacity, ecrire un load test.
license: MIT (upstream Jeffallan/claude-skills) -- adapted for LIA-SEC
allowed-tools: Read, Grep, Glob, Bash, Write, Edit
metadata:
  author: mo0ogly@proton.me
  upstream: https://github.com/Jeffallan/claude-skills/tree/main/skills/monitoring-expert
  version: "2.0.0-lia"
  domain: devops
  triggers: monitoring, observability, metrics, dashboard, alerting, RED method, USE method, load test, k6, Artillery, profiling, pprof, benchmark Go, capacity planning, Performance Monitoring, unified_logs analysis, performance_snapshots, slow query
  role: specialist
  scope: implementation
  output-format: code (Go pprof + SQL queries unified_logs + k6 JS + Grafana JSON)
  related-skills: devops-engineer, postgres-pro, debug-go, security-reviewer
  enforces-rules: R5, R6, R10, R12
---

# Monitoring Expert (LIA-SEC adaptation)

> **Stack reel LIA-SEC observability**
> - **Logs structures** : `LogSystemEvent(level, component, action, details)` -> table `unified_logs` PostgreSQL (retention 90j, purge 3h AM)
> - **Performance Monitoring API** existante : 17 endpoints (`performance_api.go`), snapshots auto 5min via goroutine
> - **AI realtime stats** : `ai_realtime_stats_api.go` 8 endpoints (engine metrics, cost, latency)
> - **Security audit** : `security_audit_db.go` events alerting (8 types)
> - **Health check** : `/api/health` + cron auto-healing */5min
>
> **Pas de** Prometheus/Grafana en place actuellement (a designer si besoin).
> **Pas de** OpenTelemetry distributed tracing (single-VPS).
> **Frontend** : `customLogger.info/error` cote React (loggerService.ts) -> backend `unified_logs`.

---

## 0. Inventaire observability existant LIA-SEC (a NE PAS dupliquer)

| Composant | Existant | Endpoint / Helper |
|-----------|----------|-------------------|
| Logs structures | `LogSystemEvent` -> `unified_logs` | `cmd/sigma_web/logs_postgres.go` |
| Frontend logs | `customLogger.info` -> backend POST | `services/loggerService.ts` |
| Performance snapshots | Goroutine 5min | `performance_api.go` (17 endpoints) |
| AI metrics | Engine stats + cost | `ai_realtime_stats_api.go` (8 endpoints) |
| Security events | Alert engine 8 types | `security_audit_db.go` (5 endpoints) |
| Health check | LB + auto-healing cron | `/api/health` + `/api/diagnostic/build-info` |
| LIA-SEC dashboards UI | Performance Dashboard React | `components/Performance*` |
| Logs purge auto | 90j retention, daily 3 AM | `logs_postgres.go startAutomaticCleanup` |

**Avant d'ajouter quoi que ce soit** : verifier si la metric/dashboard existe deja (Performance API, AI stats). Eviter doublon.

---

## 1. Workflow agentique (5 phases)

```
[1] ASSESS
    - Quel SLI / KPI manque ? (RED : Rate, Errors, Duration -- USE : Utilization, Saturation, Errors)
    - Existant suffisant ? (Performance Monitoring API repond deja)
    - Granularite : par endpoint ? par module ? par client_id (multi-tenant) ?
    - Cible : alerte temps reel ? rapport daily ? SLA report mensuel ?

[2] INSTRUMENT
    - Si event business : `LogSystemEvent("INFO", "MODULE", "ACTION", details)` (R6)
    - Si compteur perf : ajouter colonne dans `performance_snapshots` ou nouvelle table
    - Si AI cost/latency : utiliser `ai_realtime_stats_api.go` API (existant)
    - Si event securite : `LogSecurityAuditEvent` (existant 8 types)

[3] COLLECT + STORE
    - PostgreSQL = source unique (R5). Pas de Prometheus tant que volume < 1M events/jour.
    - Index : `unified_logs` deja indexe sur (timestamp DESC, level, component)
    - Si volumetrie > 10M rows/jour -> partitioning par mois (cf `/postgres-pro`)

[4] VISUALIZE
    - Composant React reutilisable : pattern `Performance*Dashboard` existant
    - Charts : Recharts (deja en place, theme-aware)
    - RED metrics : Rate, Errors, Duration en colonnes
    - USE metrics : CPU, RAM, disk, FD, goroutines (Performance API existant)

[5] ALERT
    - Pas de Prometheus AlertManager pour l'instant.
    - Pattern : query SQL periodique + LogSystemEvent("CRITICAL", ...) si seuil depasse
    - Future : si volumetrie justifie, exporter Prometheus + Grafana
```

---

## 2. Reference Guide -- charger selon le contexte

| Topic | Reference | Charger quand |
|-------|-----------|---------------|
| Structured logging | `references/structured-logging.md` | Pino/Winston *generique* -- LIA-SEC utilise `LogSystemEvent` only |
| Prometheus metrics | `references/prometheus-metrics.md` | Si Prometheus envisage (volumetrie justifiee) |
| OpenTelemetry | `references/opentelemetry.md` | Si distributed tracing requis (single-VPS = NON pour l'instant) |
| Alerting rules | `references/alerting-rules.md` | Definir seuils PromQL ou SQL equivalent |
| Dashboards | `references/dashboards.md` | RED/USE method, Grafana JSON (si Grafana adopte) |
| Performance testing | `references/performance-testing.md` | k6 / Artillery load tests |
| Application profiling | `references/application-profiling.md` | Go pprof (deja dispo via runtime/pprof import) |
| Capacity planning | `references/capacity-planning.md` | Forecasting growth, scaling plan |

---

## 3. Patterns LIA-SEC

### 3.1 Structured logging (le pattern obligatoire)

```go
// CORRECT -- structured fields, R6 compliant
LogSystemEvent("INFO", "ETL_IMPORT", "STARTED",
    fmt.Sprintf("Importing CVE batch from NVD, count=%d, source=%s", batchSize, src))

LogSystemEvent("ERROR", "DATABASE", "QUERY_FAILED",
    fmt.Sprintf("UPDATE failed for asset %s: %v", assetID, err))

LogSystemEvent("CRITICAL", "AUTH", "BRUTE_FORCE_DETECTED",
    fmt.Sprintf("IP %s attempted %d logins in 60s", ip, attempts))

// INTERDIT
fmt.Println("Importing batch...")  // R6 violation
log.Printf("Failed: %v", err)       // R6 violation (sauf 13 sites pre-init listes dans enforcement-backend.md)
```

### 3.2 Query unified_logs pour metric ad-hoc

```sql
-- Top 10 endpoints les plus lents (last 24h, basé sur logs duration_ms)
SELECT
    component,
    action,
    COUNT(*)                                              AS calls,
    AVG((details->>'duration_ms')::int)                   AS avg_ms,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY (details->>'duration_ms')::int) AS p95_ms,
    MAX((details->>'duration_ms')::int)                   AS max_ms
FROM unified_logs
WHERE timestamp > NOW() - INTERVAL '24 hours'
  AND level = 'INFO'
  AND details ? 'duration_ms'
GROUP BY component, action
ORDER BY p95_ms DESC NULLS LAST
LIMIT 10;

-- Error rate par module (RED method)
SELECT
    component,
    COUNT(*) FILTER (WHERE level IN ('ERROR','CRITICAL')) * 100.0 / COUNT(*) AS error_rate_pct,
    COUNT(*) AS total_calls
FROM unified_logs
WHERE timestamp > NOW() - INTERVAL '1 hour'
GROUP BY component
HAVING COUNT(*) > 100
ORDER BY error_rate_pct DESC;
```

### 3.3 Pattern k6 load test (LIA-SEC)

```js
// scripts/load_test_cve_search.js
import http from 'k6/http';
import { check, sleep } from 'k6';

const TOKEN = __ENV.LIA_API_TOKEN;  // Fournir via env (R8 -- pas de hardcode)
const BASE   = __ENV.LIA_BASE || 'http://localhost:8081';

export const options = {
    stages: [
        { duration: '30s', target: 5 },    // ramp
        { duration: '2m',  target: 10 },   // sustain (cible : 10 RPS, rate-limiter LIA-SEC = 60 req/min/IP)
        { duration: '30s', target: 0 },    // ramp down
    ],
    thresholds: {
        http_req_duration: ['p(95)<800'],          // P95 < 800ms (CVE search PostgreSQL fulltext)
        http_req_failed:   ['rate<0.01'],          // < 1% errors
        checks:            ['rate>0.99'],          // > 99% checks pass
    },
};

export default function () {
    const params = {
        headers: {
            Authorization: `Bearer ${TOKEN}`,
            'Content-Type': 'application/json',
        },
    };
    const res = http.get(`${BASE}/api/cve/search?q=apache&limit=20`, params);
    check(res, {
        '200 status':           (r) => r.status === 200,
        'has data envelope':    (r) => r.json('success') === true,
        'returns CVE items':    (r) => Array.isArray(r.json('data.items')),
    });
    sleep(1);
}
```

Lancer : `LIA_API_TOKEN=$(curl ... auth/login | jq -r .token) k6 run scripts/load_test_cve_search.js`

### 3.4 Profiling Go (pprof)

```go
// cmd/sigma_web/pprof_init.go (a creer si necessaire)
import _ "net/http/pprof"

func init() {
    if os.Getenv("LIA_PPROF_ENABLED") == "true" {
        go func() {
            // pprof endpoint sur localhost only (pas expose Internet)
            LogSystemEvent("INFO", "PPROF", "STARTED", "pprof on localhost:6060")
            // #nosec G114 -- localhost only, dev profiling
            http.ListenAndServe("127.0.0.1:6060", nil)
        }()
    }
}
```

```bash
# Enable profiling temporaire
sudo systemctl edit lia-backend  # ajouter Environment=LIA_PPROF_ENABLED=true
sudo systemctl restart lia-backend

# Capture profile 30s
curl http://localhost:6060/debug/pprof/profile?seconds=30 -o cpu.prof
go tool pprof -http=:8080 cpu.prof  # UI interactive

# Heap snapshot
curl http://localhost:6060/debug/pprof/heap -o heap.prof
go tool pprof -http=:8080 heap.prof

# Goroutines (debug deadlock)
curl http://localhost:6060/debug/pprof/goroutine?debug=2 > goroutines.txt
```

### 3.5 Alerte SQL periodique (sans Prometheus)

```sql
-- Cron : */5 * * * * /opt/lia-sec/scripts/check_alerts.sh
-- Le script execute cette query et logge CRITICAL si seuil depasse

WITH errors_5min AS (
    SELECT COUNT(*) AS err_count
    FROM unified_logs
    WHERE timestamp > NOW() - INTERVAL '5 minutes'
      AND level IN ('ERROR','CRITICAL')
)
SELECT
    err_count,
    CASE WHEN err_count > 50 THEN 'ALERT'
         WHEN err_count > 20 THEN 'WARN'
         ELSE 'OK' END AS status
FROM errors_5min;
```

```bash
# scripts/check_alerts.sh (exemple minimaliste)
#!/usr/bin/env bash
COUNT=$(PGPASSWORD="$LIA_DB_PASS" psql -h localhost -U lia_admin -d lia_scan -tAc \
    "SELECT COUNT(*) FROM unified_logs WHERE timestamp > NOW() - INTERVAL '5 min' AND level IN ('ERROR','CRITICAL')")
if [ "$COUNT" -gt 50 ]; then
    PGPASSWORD="$LIA_DB_PASS" psql -h localhost -U lia_admin -d lia_scan -c \
        "INSERT INTO unified_logs (level, component, action, message) VALUES \
        ('CRITICAL', 'ALERT_ENGINE', 'ERROR_RATE_HIGH', 'Errors > 50 in last 5 min: ${COUNT}')" >/dev/null
fi
```

### 3.6 Dashboard React (RED method)

Pattern existant `components/Performance*` -- pour ajouter un nouveau dashboard :

```tsx
// components/MyModule/MyMetricsDashboard.tsx
import { useEffect, useState } from 'react';
import { fetchWithConfig } from '../../config/apiConfig';
import { customLogger } from '../../services/loggerService';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
// ... MUI v7 Grid, theme-aware

export const MyMetricsDashboard = () => {
    const [data, setData] = useState([]);
    useEffect(() => {
        fetchWithConfig('/api/mymodule/metrics?window=1h')
            .then(r => r.json())
            .then(j => setData(j.data?.items ?? []))
            .catch(e => customLogger.error('METRICS', 'Failed to load', e));
    }, []);
    return (
        <ResponsiveContainer width="100%" height={300}>
            <LineChart data={data}>
                <XAxis dataKey="timestamp" />
                <YAxis />
                <Tooltip />
                <Line type="monotone" dataKey="rate"  name="Rate (req/s)" />
                <Line type="monotone" dataKey="error" name="Errors (%)" />
                <Line type="monotone" dataKey="p95"   name="P95 latency (ms)" />
            </LineChart>
        </ResponsiveContainer>
    );
};
```

---

## 4. Anti-patterns interdits

| INTERDIT | A la place |
|----------|-----------|
| `fmt.Println` / `log.Printf` pour metriques | `LogSystemEvent` (R6) |
| Logs avec PII (email, mot de passe, JWT) | Redact (`mask_email(e)` helper) |
| Alerter sur chaque ERROR (alert fatigue) | Threshold (rate, count window) ; SLO-based alerting |
| String interpolation au lieu de structured fields | `fmt.Sprintf("user=%s id=%s", u, id)` -> ok mais via JSONB `details` mieux |
| Skip correlation ID (`request_id` / `trace_id`) | Generer en debut de handler, propager dans LogSystemEvent details |
| Prometheus exporter sans justification (premature) | Rester sur `unified_logs` jusqu'a > 1M events/jour ou besoin metrique multi-process |
| Dashboard sans theme-aware (hardcoded hex) | Utiliser `theme.palette` (R8 frontend) |
| Load test sur PROD `liascan.tech` sans ROE | Local `localhost:8081` only |
| Emojis dans alertes / logs / metric names | (R10) |
| Stocker secrets en clair pour load tests | `$LIA_API_TOKEN` env var (R8) |

---

## 5. Output template

```markdown
# Monitoring Change : <feature> -- YYYY-MM-DD

## 1. Cible
- SLI / KPI : ...
- Granularite : ...
- Methode : RED | USE
- Existant ? : oui (`performance_api.go`) -> etendre | non -> creer

## 2. Instrumentation
- LogSystemEvent ajouts : ...
- Tables / colonnes ajoutees : (migration NNN si schema)

## 3. Visualisation
- Composant React : `MyMetricsDashboard.tsx` (existant ou nouveau)
- Charts : Recharts theme-aware

## 4. Alerte
- Seuil : ...
- Cron / trigger : ...
- Action : LogSystemEvent CRITICAL + (optionnel : email/Slack via worker API)

## 5. Recette
- Load test k6 (si endpoint perf-critical)
- p95 target : ...ms
- error rate target : < ...%
- profiling pprof si bottleneck identifie

## 6. Doc
- `_alire/01_DOCUMENTATION/technical/` : nouveau metric documente
- HelpButton dans le dashboard frontend (R8 + /create-ui-help)
```

---

## 6. Score agentique attendu (>= 40/50)

| Critere | Min | Comment l'atteindre |
|---------|-----|---------------------|
| C1 Decomposition | 8/10 | Workflow 5 phases respecte (ASSESS -> INSTRUMENT -> COLLECT -> VIZ -> ALERT) |
| C2 Planification (THINK) | 9/10 | Verifier existant (Performance API) AVANT instrumenter ; 2+ alternatives (PostgreSQL vs Prometheus) |
| C3 Replanification | 8/10 | Si volumetrie depasse capacity -> REPLAN (partitioning, Prometheus, time-series DB) |
| C4 Outillage | 8/10 | k6 + pprof + psql_lia AVANT proposer optimisation |
| C5 Tracabilite | 8/10 | Plan + decision_log + RETEX + Librarian Gate + commit unique |
