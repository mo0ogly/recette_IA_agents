# SCORING_CONFIG -- Configuration de scoring par defaut

> Ce fichier contient la configuration de scoring par defaut.
> A charger au debut de chaque cycle PDCA.
> Le fichier SCORING_CONFIG.json evolue a chaque phase ACT (nouveaux checks, poids ajustes, domaines ajoutes/retires).

## Structure

Le SCORING_CONFIG.json est place a la racine du repertoire `pdca/{perimetre}/`.
Il est cree au cycle 1 avec les valeurs par defaut ci-dessous, puis mis a jour a chaque A.4.

## JSON par defaut

```json
{
  "version": 3,
  "comment": "v3 (2026-06-11): backend Go -> Rust (AgentRail). SEC/TST/ARC/HYG backend checks remappes vers cargo/clippy/audit + tracing + Axum; security domain = build-pipeline-rust.md scoring /20. v2: ajout domaine code_hygiene (RETEX APEX 2026-03-18), reequilibrage poids",
  "domains": {
    "security": {
      "weight": 20,
      "checks": [
        {"id": "SEC-01", "name": "No raw fetch()", "type": "grep_count", "pattern": "await fetch(", "scope": "services/", "exclude": ["apiConfig.ts", "loggerService.ts"], "target": 0},
        {"id": "SEC-02", "name": "No hardcoded URLs", "type": "grep_count", "pattern": "localhost:8081", "target": 0},
        {"id": "SEC-03", "name": "No console.log", "type": "grep_count", "pattern": "console.log", "scope": "src/", "exclude": ["loggerService.ts"], "target": 0},
        {"id": "SEC-04", "name": "No println/dbg logging (use tracing)", "type": "grep_count", "pattern": "println!|eprintln!|dbg!", "scope": "src/", "exclude_pattern": "#\\[cfg\\(test\\)\\]", "target": 0},
        {"id": "SEC-05", "name": "No SQL injection (dynamic query)", "type": "grep_count", "pattern": "format!.*(SELECT|INSERT|UPDATE|DELETE)", "scope": "src/", "target": 0},
        {"id": "SEC-06", "name": "No vulnerable deps (RUSTSEC)", "type": "command", "cmd": "cargo audit 2>&1 | grep -cE 'Severity: (high|critical)'", "expect": "0"},
        {"id": "SEC-07", "name": "No XSS without DOMPurify", "type": "grep_count", "pattern": "dangerouslySetInnerHTML", "scope": "src/", "exclude_pattern": "DOMPurify", "target": 0},
        {"id": "SEC-08", "name": "No panic on fallible path", "type": "grep_count", "pattern": "\\.unwrap\\(\\)|\\.expect\\(|panic!", "scope": "src/", "exclude_pattern": "#\\[cfg\\(test\\)\\]|// SAFETY", "target": 0}
      ]
    },
    "testing": {
      "weight": 15,
      "checks": [
        {"id": "TST-01", "name": "Rust compiles + clippy clean", "type": "command", "cmd": "cargo build && cargo clippy --all-targets --all-features -- -D warnings", "expect": "exit 0"},
        {"id": "TST-02", "name": "React compiles (vite build)", "type": "command", "cmd": "cd sigma-react-frontend && node node_modules/.bin/vite build", "expect": "exit 0"},
        {"id": "TST-03", "name": "Rust test modules exist", "type": "command", "cmd": "grep -rlE '#\\[cfg\\(test\\)\\]|#\\[test\\]|#\\[tokio::test\\]' src/ tests/ --include='*.rs' | wc -l", "target": ">10"},
        {"id": "TST-04", "name": "React test files exist", "type": "count_files", "pattern": "*.test.ts*", "scope": "sigma-react-frontend/", "target": ">10"},
        {"id": "TST-05", "name": "NATS event bus reachable", "type": "command", "cmd": "curl -s -o /dev/null -w '%{http_code}' http://localhost:8222/healthz 2>/dev/null", "expect": "200"},
        {"id": "TST-06", "name": "Vitest passes", "type": "command", "cmd": "cd sigma-react-frontend && npx vitest run 2>/dev/null", "expect": "exit 0"},
        {"id": "TST-07", "name": "No null .map() crashes", "type": "grep_count", "pattern": "\\.[a-z]+\\.map\\(", "scope": "sigma-react-frontend/src/", "exclude_pattern": "|| \\[\\]", "description": "Every .property.map() must have || [] guard. Incident 2026-04-06: 9 components crashed in prod."},
        {"id": "TST-08", "name": "Runtime smoke test (Playwright)", "type": "manual", "description": "Navigate to 5 main pages with Playwright, verify 0 Component Error in snapshot. Pages: Dashboard, Discovery, Analysis, Admin, Compliance."}
      ]
    },
    "architecture": {
      "weight": 15,
      "checks": [
        {"id": "ARC-01", "name": "tracing instrumentation adoption", "type": "adoption_rate", "pattern": "tracing::|#\\[instrument", "scope": "src/**/*.rs", "target": ">80%", "description": "Structured logging via tracing, not println"},
        {"id": "ARC-02", "name": "customLogger adoption", "type": "adoption_rate", "pattern": "customLogger", "scope": "sigma-react-frontend/src/services/*.ts", "target": ">80%"},
        {"id": "ARC-03", "name": "Control-plane mediation (I2)", "type": "manual", "description": "No direct agent->external path bypassing the Gateway; all side-effects via controlled proxies (I5)"},
        {"id": "ARC-04", "name": "Migrations numbered", "type": "count_files", "pattern": "migrations/*.sql", "scope": "migrations/"},
        {"id": "ARC-05", "name": "Axum CORS layer present", "type": "grep_count", "pattern": "CorsLayer", "scope": "src/", "target": ">0", "description": "Gateway router applies a tower-http CorsLayer (deny-by-default policy)"}
      ]
    },
    "code_hygiene": {
      "weight": 15,
      "comment": "Nouveau domaine v2 -- RETEX APEX 2026-03-18 (10/14 fichiers etaient dead code)",
      "checks": [
        {"id": "HYG-01", "name": "No stub handlers", "type": "grep_count", "pattern": "todo!\\(\\)|unimplemented!\\(\\)|StatusCode::NOT_IMPLEMENTED", "scope": "src/", "target": 0, "description": "Aucun handler todo!()/unimplemented!()/501 dans le code actif"},
        {"id": "HYG-02", "name": "No dead code (compiler)", "type": "command", "cmd": "cargo build 2>&1 | grep -cE 'never used|unused import|unused variable'", "expect": "0"},
        {"id": "HYG-03", "name": "Dead code ratio < 10%", "type": "dead_code_ratio", "description": "Symboles publics avec 0 appels externes < 10% du total (voir triage C.0)"},
        {"id": "HYG-04", "name": "No emoji in code/docs", "type": "grep_count", "pattern": "[\\x{1F600}-\\x{1F64F}\\x{1F300}-\\x{1F5FF}\\x{1F680}-\\x{1F6FF}\\x{2600}-\\x{26FF}]", "scope": "src/,sigma-react-frontend/src/", "target": 0},
        {"id": "HYG-05", "name": "MUI v7 Grid syntax", "type": "grep_count", "pattern": "<Grid item |<Grid.*item ", "scope": "sigma-react-frontend/src/", "target": 0, "description": "Ancienne syntaxe MUI v5/v6 interdite"},
        {"id": "HYG-06", "name": "No hardcoded fontFamily", "type": "grep_count", "pattern": "fontFamily:.*['\"]monospace['\"]|fontFamily:.*['\"]Arial|fontFamily:.*['\"]Fira Code", "scope": "sigma-react-frontend/src/components/", "target": 0, "description": "Utiliser fontFamily: 'inherit' ou theme.typography.fontFamily"},
        {"id": "HYG-07", "name": "Chip borderRadius: 1", "type": "manual", "description": "Tous les composants Chip MUI ont borderRadius: 1 (pas oval par defaut). Verifier via grep -rn 'Chip' dans le perimetre"},
        {"id": "HYG-08", "name": "No mock/placeholder data", "type": "grep_count", "pattern": "mock[Dd]ata|MOCK_|fakeDat|dummyDat|lorem ipsum|example\\.com", "scope": "src/,sigma-react-frontend/src/", "target": 0}
      ]
    },
    "completeness": {
      "weight": 15,
      "checks": [
        {"id": "CMP-01", "name": "CRUD endpoints complete", "type": "manual"},
        {"id": "CMP-02", "name": "Frontend connected", "type": "manual"},
        {"id": "CMP-03", "name": "No TODO/placeholder", "type": "grep_count", "pattern": "TODO|FIXME|placeholder|PLACEHOLDER", "target": 0}
      ]
    },
    "documentation": {
      "weight": 10,
      "checks": [
        {"id": "DOC-01", "name": "Module docs exist", "type": "file_exists", "path": "_alire/01_DOCUMENTATION/"},
        {"id": "DOC-02", "name": "API documented", "type": "manual"},
        {"id": "DOC-03", "name": "CLAUDE.md current", "type": "file_exists", "path": "CLAUDE.md"},
        {"id": "DOC-04", "name": "UI Help content exists", "type": "grep_count", "pattern": "HelpButton|useHelp", "scope": "sigma-react-frontend/src/components/{perimetre}*/", "target": ">0", "description": "Les ecrans du perimetre doivent avoir des HelpButton integres et du contenu dans ui_help_content"}
      ]
    },
    "benchmark_parity": {
      "weight": 10,
      "checks": [
        {"id": "BNC-01", "name": "Feature parity", "type": "gap_count", "description": "Number of features in benchmark absent from AgentRail"},
        {"id": "BNC-02", "name": "Unique advantages", "type": "manual", "description": "Features in AgentRail absent from benchmark"},
        {"id": "BNC-03", "name": "No regression", "type": "delta_check", "description": "No domain score decreased vs previous cycle"}
      ]
    }
  }
}
```

## Explication des types de checks

| Type | Description | Champs |
|------|-------------|--------|
| `grep_count` | Compte les occurrences d'un pattern. `target: 0` = aucune occurrence attendue | `pattern`, `scope`, `exclude`, `target` |
| `command` | Execute une commande shell. Verifie le code retour | `cmd`, `expect` |
| `count_files` | Compte les fichiers correspondant au pattern | `pattern`, `scope`, `target` |
| `adoption_rate` | Pourcentage de fichiers du scope qui contiennent le pattern | `pattern`, `scope`, `target` |
| `file_exists` | Verifie l'existence d'un fichier ou repertoire | `path` |
| `gap_count` | Nombre de gaps identifies (benchmark vs AgentRail) | `description` |
| `delta_check` | Verifie que le score n'a pas baisse vs cycle precedent | `description` |
| `manual` | Check manuel -- l'agent doit evaluer et justifier | `description` |

## Scoring methodology -- N/A domains (R18, BLOCKING)

A domain whose checks ALL yield `N/A` (no data source available in the
current run) MUST be **excluded** from the weighted total, and the
remaining domains **renormalized** over their summed weight. It MUST NOT
be defaulted to an arbitrary baseline (e.g. 50).

Canonical case: `benchmark_parity` (weight 10) when no `--benchmark`
repo is provided -- BNC-01 (`gap_count`) and BNC-02 (`manual`) have no
input, so the domain is unmeasurable. (BNC-03 `delta_check` alone is a
cross-cycle regression guard, not an external-parity measure, and does
not by itself justify anchoring a 10%-weight domain.)

Formula when one or more domains are excluded:

```
score = ( sum( weight_d * score_d ) for d in MEASURED ) / sum( weight_d for d in MEASURED )
```

Example: benchmark_parity excluded -> renormalize over `sum(weights) =
0.90` (the other six domains).

Rationale (R18): an arbitrary `50` for an unmeasured domain is a number
that is neither measured nor justified -- it silently caps every
no-benchmark audit at ~95 and drags realistic scores down ~5 absolute
points. That is a scoring-methodology defect, not a property of the
audited code. Incident 2026-05-16: the 5-cycle `backend-go-global`
audit was reported at 80.05 while the honestly-renormalized figure
(benchmark_parity excluded, plus correction of a security domain
internally inconsistent at 78 with 10/10 SEC checks PASS) was 89.17.
Excluding > defaulting.

A domain may only be re-included once a real data source exists (e.g.
`--benchmark <repo>` is passed and BNC checks produce real gap counts).

## Evolution du SCORING_CONFIG

A chaque phase A.4 (RETEX), le SCORING_CONFIG evolue :

- **AJOUTER checks** : nouveau check ID, type, query, justification
- **RETIRER checks** : check ID, raison (faux positif, obsolete)
- **AJUSTER poids** : domaine, ancien poids -> nouveau poids, justification
- **NOUVEAU domaine** : nom, poids, checks initiaux

Le champ `version` est incremente a chaque modification.
