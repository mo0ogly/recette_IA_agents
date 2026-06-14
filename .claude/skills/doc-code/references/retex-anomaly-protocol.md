# RETEX Anomaly Protocol -- Surfacing Discoveries During Documentation

Documentation is a magnifying glass on the codebase.
When agents READ code to document it, they often discover issues invisible during normal development.
This protocol ensures those discoveries are captured and surfaced.

---

## What Counts as an Anomaly

An anomaly is anything unexpected, incorrect, or concerning found while reading code for documentation purposes.

### Categories

| Category | Examples | Severity |
|----------|----------|----------|
| `DEAD_CODE` | Function with 0 callers, unused imports, commented-out blocks | LOW |
| `SECURITY` | Missing input validation, SQL without parameterization, hardcoded secrets | CRITICAL |
| `COMPLIANCE` | Missing setCORSHeaders, fetch() without fetchWithConfig, console.log in prod | HIGH |
| `ARCHITECTURE` | Circular dependencies, god files (>800 LOC), duplicated logic | MEDIUM |
| `PERFORMANCE` | N+1 queries, missing pagination, unbounded loops | MEDIUM |
| `INCONSISTENCY` | Doc says X but code does Y, route registered but handler empty | HIGH |
| `MISSING_TEST` | Handler >200 LOC without _test.go, component without .test.tsx | MEDIUM |
| `TECH_DEBT` | Deprecated API usage, TODO comments, legacy patterns | LOW |

---

## Collection Process

### During Agent Execution

Every swarm agent has an `ANOMALIES DETECTED` section in their output.
This is MANDATORY even if empty:

```markdown
### ANOMALIES DETECTED
- [SECURITY] hardcoded API key in line 45 of discovery_api.go
- [DEAD_CODE] function handleLegacyExport() has 0 callers
- [COMPLIANCE] missing setCORSHeaders in handleGetMetrics (line 112)
- None found.   <- Also acceptable
```

### During QA

The QA agent cross-references documentation against code and may find additional anomalies:

```markdown
### ANOMALIES SURFACED
- [INCONSISTENCY] Doc claims 12 endpoints but code has 14
- [MISSING_TEST] remediation_tracking_api.go (890 LOC) has no _test.go
```

### During Recette

The Recette agent consolidates ALL anomalies from all sources into a single table.

---

## Anomaly Report Format

The Recette agent produces this in `_alire/01_DOCUMENTATION/{module}/RECETTE_{module}_{YYYY-MM-DD}.md`:

```markdown
## Anomaly Report

### Summary
| Severity | Count |
|----------|-------|
| CRITICAL | {N} |
| HIGH | {N} |
| MEDIUM | {N} |
| LOW | {N} |
| **Total** | **{N}** |

### Details

| # | Category | Severity | File | Line | Description | Source Agent | Recommended Action |
|---|----------|----------|------|------|-------------|-------------|-------------------|
| 1 | SECURITY | CRITICAL | discovery_api.go | 45 | Hardcoded API key | BackendSpec | Remove, use env var |
| 2 | DEAD_CODE | LOW | legacy_export.go | - | 0 callers for handleLegacyExport | BackendSpec | Archive (.disabled) |
| 3 | COMPLIANCE | HIGH | metrics_api.go | 112 | Missing setCORSHeaders | BackendSpec | Add setCORSHeaders |
| 4 | INCONSISTENCY | HIGH | compliance_api_en.md | 34 | Doc says 12 endpoints, code has 14 | QA | Update doc |
```

---

## Escalation Rules

| Severity | Action |
|----------|--------|
| CRITICAL | **IMMEDIATE**: Alert user in final output. Do NOT continue to commit without acknowledgment. |
| HIGH | **REPORT**: Include in RETEX. Recommend fix in next cycle. |
| MEDIUM | **LOG**: Include in RETEX. Add to tech debt backlog. |
| LOW | **NOTE**: Include in RETEX for awareness. No action required. |

---

## Integration with RETEX

At the end of every doc-code execution, the Program Director:

1. Reads the Recette anomaly report
2. If CRITICAL anomalies exist:
   - Display them prominently to the user
   - Do NOT auto-commit until acknowledged
3. If HIGH+ anomalies exist:
   - Create `_alire/02_LOGS/RETEX_DOC_CODE_{MODULE}_{YYYY-MM-DD}.md`
   - Include the full anomaly table
   - Include recommended actions
   - Link to the Recette report

### RETEX File Format

```markdown
# RETEX -- doc-code {module} -- {YYYY-MM-DD}

## Context
- Module documented: {module}
- Files in scope: {count}
- QA score: {XX}/100

## Anomalies Discovered

{Copy the anomaly table from Recette report}

## Impact Assessment
- {N} CRITICAL issues require immediate attention
- {N} HIGH issues should be fixed in the next PDCA cycle
- {N} MEDIUM issues added to tech debt backlog

## Recommended Actions
1. {Specific action for anomaly #1}
2. {Specific action for anomaly #2}
...

## Lessons Learned
- {What the documentation process revealed about the codebase}
- {Patterns to watch for in future documentation cycles}
```

---

## Why This Matters

Documentation-driven discovery is one of the most valuable side effects of structured documentation.
By requiring every agent to report anomalies:

1. **Security issues** surface before they reach production
2. **Dead code** is identified for cleanup
3. **Inconsistencies** between code and existing docs are caught
4. **Technical debt** is cataloged systematically
5. **Architecture concerns** are flagged for review

The cost of reading code to document it is already paid.
Anomaly surfacing extracts maximum value from that investment.
