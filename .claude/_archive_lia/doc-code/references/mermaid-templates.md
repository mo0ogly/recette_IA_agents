# Mermaid Diagram Templates - LIA-SEC

JSON input examples for generate_mermaid.py. Each section = one diagram type.
Copy, adapt, run the generator.

Available themes: `dark` (default), `cyber`, `professional`
Available node types: `backend`, `frontend`, `database`, `api`, `service`, `middleware`, `external`, `security`, `critical`, `warning`, `success`, `queue`, `cache`, `monitoring`

---

## Architecture Diagram

```bash
python3 .claude/skills/doc-code/scripts/generate_mermaid.py architecture input.json -o output.mmd --theme dark
```

```json
{
  "title": "LIA-SEC Platform Architecture",
  "direction": "TD",
  "subgraphs": [
    {"id": "frontend_layer", "label": "Frontend Layer", "members": ["react_app"]},
    {"id": "backend_layer", "label": "Backend Layer", "members": ["go_backend", "ai_manager"]},
    {"id": "data_layer", "label": "Data Layer", "members": ["postgresql", "redis_cache"]}
  ],
  "components": [
    {
      "id": "react_app",
      "label": "React 19 SPA\n314 components",
      "type": "frontend",
      "shape": "rect",
      "connects_to": [
        {"id": "go_backend", "label": "REST/JWT", "style": "solid"},
        {"id": "go_backend", "label": "WebSocket", "style": "dashed"}
      ]
    },
    {
      "id": "go_backend",
      "label": "Go Backend\n560+ routes",
      "type": "backend",
      "shape": "rect",
      "connects_to": [
        {"id": "postgresql", "label": "pg/sql", "style": "solid"},
        {"id": "redis_cache", "label": "cache", "style": "dashed"},
        {"id": "ai_manager", "label": "internal", "style": "solid"}
      ]
    },
    {
      "id": "ai_manager",
      "label": "UniversalAIManager\nGroq / Ollama fallback",
      "type": "service",
      "shape": "rect",
      "connects_to": [
        {"id": "groq_api", "label": "HTTPS", "style": "dashed"},
        {"id": "ollama_local", "label": "HTTP", "style": "dashed"}
      ]
    },
    {
      "id": "postgresql",
      "label": "PostgreSQL 17\n268 tables / 332K CVE",
      "type": "database",
      "shape": "cylinder",
      "connects_to": []
    },
    {
      "id": "redis_cache",
      "label": "Redis Cache",
      "type": "cache",
      "shape": "cylinder",
      "connects_to": []
    },
    {
      "id": "groq_api",
      "label": "Groq API\n(external)",
      "type": "external",
      "shape": "stadium",
      "connects_to": []
    },
    {
      "id": "ollama_local",
      "label": "Ollama Local\nembeddings only",
      "type": "service",
      "shape": "stadium",
      "connects_to": []
    }
  ]
}
```

---

## Sequence Diagram (API Flow)

```bash
python3 .claude/skills/doc-code/scripts/generate_mermaid.py sequence input.json --theme dark --embed-md -o diagram.md
```

```json
{
  "title": "JWT Authentication Flow",
  "autonumber": true,
  "participants": [
    {"id": "Browser", "label": "Browser / React", "type": "actor"},
    {"id": "Backend", "label": "Go Backend", "type": "participant"},
    {"id": "DB",      "label": "PostgreSQL",   "type": "participant"}
  ],
  "interactions": [
    {
      "from": "Browser", "to": "Backend",
      "action": "POST /api/auth/login {email, password}",
      "type": "sync"
    },
    {
      "from": "Backend", "to": "DB",
      "action": "SELECT user WHERE email=?",
      "response": "user row + hashed password",
      "type": "async"
    },
    {
      "from": "Backend", "to": "Browser",
      "action": "bcrypt.CompareHashAndPassword()",
      "type": "sync",
      "note": "Constant-time comparison",
      "note_pos": "right"
    },
    {
      "from": "Backend", "to": "Browser",
      "action": "200 {token: JWT, expires: 24h}",
      "type": "return"
    },
    {
      "from": "Browser", "to": "Backend",
      "action": "GET /api/compliance/score\nAuthorization: Bearer <JWT>",
      "response": "200 {score: 87, framework: anssi}",
      "type": "async",
      "note": "fetchWithConfig injects JWT",
      "note_pos": "over",
      "end": true
    }
  ]
}
```

---

## ER Diagram (PostgreSQL Schema)

```bash
python3 .claude/skills/doc-code/scripts/generate_mermaid.py er input.json --theme professional -o model.mmd
```

```json
{
  "title": "CVE Data Model",
  "entities": [
    {
      "name": "cve_nvd_data",
      "attributes": [
        {"type": "varchar(20)",  "name": "cve_id",        "key": "PK"},
        {"type": "decimal(4,1)", "name": "cvss_score",    "key": ""},
        {"type": "varchar(10)",  "name": "severity",      "key": ""},
        {"type": "text",         "name": "description",   "key": ""},
        {"type": "jsonb",        "name": "cpe_matches",   "key": ""},
        {"type": "timestamp",    "name": "published_date","key": ""},
        {"type": "timestamp",    "name": "updated_at",    "key": ""}
      ],
      "relations": [
        {"to": "cisa_kev",    "cardinality": "||--o{", "label": "tracked in"},
        {"to": "exploit_db",  "cardinality": "||--o{", "label": "exploited by"},
        {"to": "rule_cve_map","cardinality": "||--o{", "label": "detected by"}
      ]
    },
    {
      "name": "cisa_kev",
      "attributes": [
        {"type": "varchar(20)",  "name": "cve_id",           "key": "PK FK", "comment": "FK -> cve_nvd_data"},
        {"type": "date",         "name": "date_added",       "key": ""},
        {"type": "date",         "name": "due_date",         "key": ""},
        {"type": "text",         "name": "required_action",  "key": ""},
        {"type": "boolean",      "name": "ransomware_use",   "key": ""}
      ],
      "relations": []
    },
    {
      "name": "exploit_db",
      "attributes": [
        {"type": "integer",     "name": "exploit_id",   "key": "PK"},
        {"type": "varchar(20)", "name": "cve_id",       "key": "FK"},
        {"type": "varchar(50)", "name": "type",         "key": ""},
        {"type": "text",        "name": "description",  "key": ""},
        {"type": "date",        "name": "published",    "key": ""}
      ],
      "relations": []
    },
    {
      "name": "rule_cve_map",
      "attributes": [
        {"type": "integer",     "name": "id",        "key": "PK"},
        {"type": "varchar(20)", "name": "cve_id",    "key": "FK"},
        {"type": "varchar(100)","name": "rule_id",   "key": ""},
        {"type": "varchar(50)", "name": "technology","key": ""}
      ],
      "relations": []
    }
  ]
}
```

---

## Component Tree (React)

```bash
python3 .claude/skills/doc-code/scripts/generate_mermaid.py component input.json --theme dark -o component_tree.mmd
```

```json
{
  "title": "CVE Explorer Component Tree",
  "components": [
    {
      "id": "CVEExplorer",
      "label": "CVEExplorer (Page)",
      "type": "frontend",
      "shape": "rect",
      "children": [
        {
          "id": "CVESearch",
          "label": "CVESearch",
          "type": "frontend",
          "note": "uses fetchWithConfig",
          "children": [
            {"id": "SearchBar",    "label": "SearchBar",    "type": "frontend"},
            {"id": "FilterPanel",  "label": "FilterPanel",  "type": "frontend"}
          ]
        },
        {
          "id": "CVEDetail",
          "label": "CVEDetail",
          "type": "frontend",
          "children": [
            {"id": "CVSSGauge",    "label": "CVSSGauge",    "type": "frontend"},
            {"id": "KEVBadge",     "label": "KEVBadge",     "type": "frontend"},
            {"id": "EPSSChart",    "label": "EPSSChart",    "type": "frontend"},
            {"id": "AttackChain",  "label": "AttackChain",  "type": "api",      "note": "-> CveAttackChain"}
          ]
        },
        {
          "id": "CVEService",
          "label": "cveExplorerService.ts",
          "type": "service",
          "note": "/api/cve/*"
        }
      ]
    }
  ]
}
```

---

## Flow Diagram (Process / Workflow)

```bash
python3 .claude/skills/doc-code/scripts/generate_mermaid.py flow input.json --theme cyber -o flow.mmd
```

```json
{
  "title": "Rule Validation Pipeline",
  "direction": "TD",
  "nodes": [
    {"id": "start",      "label": "Rule submitted",     "shape": "start",    "type": "success"},
    {"id": "recipe",     "label": "Recipe validation\n41 checks", "shape": "process", "type": "backend"},
    {"id": "recipe_ok",  "label": "Recipe passed?",     "shape": "decision", "type": "api"},
    {"id": "ultimate",   "label": "Ultimate validation\n91 checks", "shape": "process", "type": "backend"},
    {"id": "ultimate_ok","label": "Ultimate passed?",   "shape": "decision", "type": "api"},
    {"id": "reportrule", "label": "ReportRule JSON\n8 checks", "shape": "process", "type": "backend"},
    {"id": "report_ok",  "label": "ReportRule passed?", "shape": "decision", "type": "api"},
    {"id": "commit",     "label": "Commit allowed",     "shape": "end",      "type": "success"},
    {"id": "fail",       "label": "Fix required",       "shape": "end",      "type": "critical"}
  ],
  "edges": [
    {"from": "start",      "to": "recipe",      "style": "solid"},
    {"from": "recipe",     "to": "recipe_ok",   "style": "solid"},
    {"from": "recipe_ok",  "to": "ultimate",    "label": "YES", "style": "solid"},
    {"from": "recipe_ok",  "to": "fail",        "label": "NO",  "style": "dashed"},
    {"from": "ultimate",   "to": "ultimate_ok", "style": "solid"},
    {"from": "ultimate_ok","to": "reportrule",  "label": "YES", "style": "solid"},
    {"from": "ultimate_ok","to": "fail",        "label": "NO",  "style": "dashed"},
    {"from": "reportrule", "to": "report_ok",   "style": "solid"},
    {"from": "report_ok",  "to": "commit",      "label": "YES", "style": "thick"},
    {"from": "report_ok",  "to": "fail",        "label": "NO",  "style": "dashed"}
  ]
}
```

---

## Gantt Diagram (PDCA / Timeline / Kill Chain)

```bash
python3 .claude/skills/doc-code/scripts/generate_mermaid.py gantt input.json --theme dark --embed-md -o pdca.md
```

```json
{
  "title": "PDCA Cycle 3 - Remediation Tracking",
  "dateFormat": "YYYY-MM-DD",
  "axisFormat": "%b %d",
  "excludes": "weekends",
  "sections": [
    {
      "name": "Plan",
      "tasks": [
        {"id": "p1", "label": "Requirements analysis", "status": "done", "start": "2026-03-01", "duration": "3d"},
        {"id": "p2", "label": "Architecture design",   "status": "done", "after": "p1", "duration": "2d"}
      ]
    },
    {
      "name": "Do",
      "tasks": [
        {"id": "d1", "label": "Backend implementation", "status": "active", "after": "p2", "duration": "5d"},
        {"id": "d2", "label": "Frontend integration",                       "after": "d1", "duration": "3d"}
      ]
    },
    {
      "name": "Check",
      "tasks": [
        {"id": "c1", "label": "Unit testing",        "status": "crit", "after": "d2", "duration": "2d"},
        {"id": "c2", "label": "Integration testing",                   "after": "c1", "duration": "1d"}
      ]
    },
    {
      "name": "Act",
      "tasks": [
        {"id": "a1", "label": "Deployment to production", "status": "crit", "after": "c2", "duration": "1d"},
        {"id": "a2", "label": "Documentation update",                        "after": "a1", "duration": "1d"}
      ]
    }
  ]
}
```

**Task status values:**
| Value | Appearance | Use case |
|-------|-----------|----------|
| `done` | Grey | Completed tasks |
| `active` | Blue | In progress |
| `crit` | Red | Critical path |
| `done,crit` | Red/Grey | Completed critical |
| `active,crit` | Red | Active critical |
| _(empty)_ | Default | Planned |

---

## Available Node Types (palette)

```bash
python3 .claude/skills/doc-code/scripts/generate_mermaid.py architecture dummy.json --list-palette
```

| Type | Fill | Stroke | Text | Usage |
|------|------|--------|------|-------|
| `backend` | #0d1b2a | #1e6091 | #a8dadc | Go handlers, services |
| `frontend` | #1a1a2e | #7b2d8b | #e8b4f8 | React components |
| `database` | #0a1628 | #e76f51 | #f4a261 | PostgreSQL, SQLite |
| `api` | #0f3460 | #00b4d8 | #90e0ef | REST endpoints, routers |
| `service` | #1b1f3b | #06d6a0 | #80ffdb | Internal services, AI |
| `middleware` | #162032 | #4361ee | #a8c8ff | JWT, CORS, rate limiter |
| `external` | #2d2d2d | #adb5bd | #dee2e6 | 3rd party APIs |
| `security` | #3d0000 | #e63946 | #ffd6d6 | Auth, security controls |
| `critical` | #4a0000 | #ff0000 | #ffaaaa | Errors, blockers |
| `warning` | #3d2800 | #f4a261 | #ffe5c0 | Alerts, degraded state |
| `success` | #003d1a | #06d6a0 | #b7f4cc | OK, validated, healthy |
| `queue` | #1c2833 | #f39c12 | #fdebd0 | n8n, job queues |
| `cache` | #1a0533 | #9b59b6 | #e8daef | Redis, in-memory cache |
| `monitoring` | #0a2626 | #27ae60 | #abebc6 | Metrics, observability |
