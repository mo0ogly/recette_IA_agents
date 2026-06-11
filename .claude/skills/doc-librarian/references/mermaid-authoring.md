# Mermaid Authoring Guide -- LIA-SEC

Quick reference for creating, fixing, and maintaining Mermaid diagrams in the
LIA-SEC documentation pipeline.

---

## Mandatory Init Block (EVERY .mmd file)

```
%%{init: {'theme': 'dark', 'themeVariables': {'primaryColor': '#0d1b2a', 'primaryTextColor': '#a8dadc', 'primaryBorderColor': '#1e6091', 'lineColor': '#00b4d8', 'secondaryColor': '#1a1a2e', 'tertiaryColor': '#0f3460', 'background': '#050d1a', 'mainBkg': '#0d1b2a', 'nodeBorder': '#1e6091', 'clusterBkg': '#0f1e30', 'titleColor': '#90e0ef', 'edgeLabelBackground': '#0f3460', 'fontSize': '14px', 'fontFamily': 'JetBrains Mono, monospace'}}}%%
```

**This block is mandatory for all `.mmd` files in `_alire/01_DOCUMENTATION/diagrams/`.**
Without it, `mmdc` will render with default white theme and `render_diagrams.sh` will
produce inconsistent SVG output.

> NOTE (2026-05-29): render_diagrams.sh / SVG pre-rendering is VESTIGIAL -- the actual rendering is client-side (mermaidClient.js, dark theme global). diagrams/svg/ is not consumed by any .md file and is empty. Do not install mmdc for this reason. See _alire/01_DOCUMENTATION/architecture/mermaid_render_pipeline_arch_en.md.

---

## Type Selection

| Use case | Diagram type | Syntax keyword |
|----------|-------------|----------------|
| System/service topology | architecture-beta | `architecture-beta` |
| Software architecture (context/container/component) | C4 | `C4Context` / `C4Container` / `C4Component` |
| Process / decision tree | Flowchart | `flowchart TD` |
| API call sequence / auth flow | Sequence | `sequenceDiagram` |
| Database schema | ERD | `erDiagram` |
| Class hierarchy / domain model | Class | `classDiagram` |
| Timeline / kill chain / sprint | Gantt | `gantt` |
| State machine | State | `stateDiagram-v2` |

**Rule**: use `architecture-beta` for cloud/infra topology. Use `C4Container` for
software architecture views (what container talks to what). Use `flowchart` for
processes. Do NOT mix paradigms in one diagram.

---

## File Naming Convention

```
_alire/01_DOCUMENTATION/diagrams/{module}_{type}.mmd
_alire/01_DOCUMENTATION/diagrams/{module}_{type}.json   <- descriptor for generate_mermaid.py
```

Examples:
- `platform_arch.mmd` -- VPS architecture (architecture-beta)
- `cve_pipeline_flow.mmd` -- CVE ETL pipeline (flowchart)
- `auth_sequence.mmd` -- JWT auth flow (sequenceDiagram)
- `cve_schema_er.mmd` -- CVE core schema (erDiagram)

---

## Quick Start Templates

### flowchart (process / decision)

```
%%{init: ...}%%
flowchart TD
    Start([Entry point]) --> Step1[Action]
    Step1 --> Decision{Condition?}
    Decision -->|Yes| Happy[Happy path]
    Decision -->|No| Error[Error path]
    Happy --> End([Exit])

    style Start fill:#003d1a,stroke:#06d6a0,color:#b7f4cc
    style End fill:#003d1a,stroke:#06d6a0,color:#b7f4cc
    style Error fill:#4a0000,stroke:#ff0000,color:#ffaaaa
```

### sequenceDiagram (API flow)

```
%%{init: ...}%%
sequenceDiagram
    autonumber
    actor User
    participant Frontend as React Frontend
    participant Backend as Go Backend :8081
    participant DB as PostgreSQL

    User->>+Frontend: Action
    Frontend->>+Backend: POST /api/endpoint
    Backend->>+DB: SELECT ...
    DB-->>-Backend: result
    Backend-->>-Frontend: 200 {success, data}
    Frontend-->>-User: Update UI
```

### erDiagram (database schema)

```
%%{init: ...}%%
erDiagram
    TABLE_A ||--o{ TABLE_B : "has"

    TABLE_A {
        varchar id PK
        varchar name "NOT NULL"
        timestamp created_at "DEFAULT NOW()"
        timestamp updated_at
    }

    TABLE_B {
        integer id PK
        varchar table_a_id FK "NOT NULL"
        text description
    }
```

### architecture-beta (infrastructure)

```
%%{init: ...}%%
architecture-beta
    group internet(cloud)[Internet]
    group vps(server)[VPS liascan.tech :443]

    service browser(internet)[Browser] in internet
    service nginx(server)[Nginx :443] in vps
    service backend(server)[Go Backend :8081] in vps
    service postgres(database)[PostgreSQL :5432] in vps

    browser:R --> L:nginx
    nginx:R --> L:backend
    backend:B --> T:postgres
```

### C4Container (software architecture)

```
%%{init: ...}%%
C4Container
    title Container Diagram -- Module Name

    Person(user, "User Role")

    Container_Boundary(system, "LIA-SEC Platform") {
        Container(frontend, "React Frontend", "React 19 / TypeScript", "SPA")
        Container(backend, "Go Backend", "Go 1.25", "REST API :8081")
        ContainerDb(db, "PostgreSQL 17", "PostgreSQL", "268 tables")
    }

    Rel(user, frontend, "Uses", "HTTPS/443")
    Rel(frontend, backend, "API calls", "HTTPS/JWT")
    Rel(backend, db, "Reads/writes", "SQL/TCP:5432")
```

---

## Common Fix Patterns

### Fix 1: Missing %%{init}%% block

```bash
# Detect
grep -rL '%%{init' _alire/01_DOCUMENTATION/diagrams/*.mmd

# Fix (manual): prepend the init block at line 1
# Use Edit tool: old_string = first line, new_string = init_block + "\n" + first_line
```

### Fix 2: Wrapped in markdown fence

`.mmd` files must NOT contain ` ```mermaid ``` ` fences. They contain raw Mermaid only.

```bash
# Detect
grep -rl "^\`\`\`mermaid" _alire/01_DOCUMENTATION/diagrams/

# Fix: remove the fence lines (first and last line)
# The file should start directly with %%{init}%% or the diagram keyword
```

### Fix 3: Multiline participant names

```
# BROKEN (causes parse error)
participant Main as Main Context
(Orchestrator)

# FIXED
participant Main as Main Orchestrator
```

### Fix 4: Unquoted special characters

```
# BROKEN
service api(server)[Go Backend :8081] in vps

# FIXED -- colon in label is usually fine in architecture-beta
# If it still fails, quote the label:
service api(server)["Go Backend :8081"] in vps
```

---

## Rendering Commands

> NOTE (2026-05-29): render_diagrams.sh / SVG pre-rendering is VESTIGIAL -- the actual rendering is client-side (mermaidClient.js, dark theme global). diagrams/svg/ is not consumed by any .md file and is empty. Do not install mmdc for this reason. See _alire/01_DOCUMENTATION/architecture/mermaid_render_pipeline_arch_en.md.

```bash
# Pre-render all Category A diagrams (stable, committed)
bash .claude/skills/doc-librarian/scripts/render_diagrams.sh

# Render a single diagram manually
mmdc -i _alire/01_DOCUMENTATION/diagrams/platform_arch.mmd \
     -o _alire/01_DOCUMENTATION/diagrams/svg/platform_arch.svg \
     -b "#050d1a"

# Validate before rendering (syntax check only -- exit 0 = OK)
mmdc -i diagram.mmd -o /dev/null 2>&1

# Generate via generate_mermaid.py (preferred for new diagrams)
python3 .claude/skills/doc-code/scripts/generate_mermaid.py \
  architecture platform_arch.json -o platform_arch.mmd --theme dark
```

---

## Checklist: New .mmd File

- [ ] File lives in `_alire/01_DOCUMENTATION/diagrams/`
- [ ] Filename: `{module}_{type}.mmd` (lowercase, no spaces)
- [ ] First line: `%%{init}%%` block (full LIA-SEC dark theme)
- [ ] No markdown fence wrappers
- [ ] Companion `.json` descriptor created (for generate_mermaid.py)
- [ ] SVG pre-rendered: `mmdc -i file.mmd -o svg/file.svg`
- [ ] Verify gate passes: `grep -L '%%{init' diagrams/*.mmd` returns nothing

---

## Full Syntax References

For complete syntax, examples, and LIA-SEC-specific patterns, see the doc-code references:

| Reference | Content |
|-----------|---------|
| `doc-code/references/mermaid-syntax-guide.md` | Type selection, best practices |
| `doc-code/references/mermaid-flowcharts.md` | Node shapes, connections, subgraphs |
| `doc-code/references/mermaid-sequence-diagrams.md` | Sequence + LIA-SEC JWT flow |
| `doc-code/references/mermaid-erd-diagrams.md` | ERD + LIA-SEC CVE schema |
| `doc-code/references/mermaid-c4-diagrams.md` | C4 + LIA-SEC platform diagrams |
| `doc-code/references/mermaid-architecture-diagrams.md` | architecture-beta + VPS topology |
| `doc-code/references/mermaid-class-diagrams.md` | Classes, relationships |
| `doc-code/references/mermaid-advanced-features.md` | Theming, ELK layout, export options |
