# Phase 1 -- DISCOVERY

**Goal:** Build a factual inventory of the product. NO marketing claims, NO superlatives, NO invention. Every feature is verified in the codebase or in the product website. Every metric has a verifiable command.

**Complexity:** COMPLEX
**Dependencies:** Phase 0 G1 validated
**Output:** platform/features_inventory.md, platform/architecture_summary.md, platform/metrics.md, platform/screenshots/*.png

## Why this phase exists

Investors smell BS. The deck must reflect what the product actually does, not what we wish it did. Phase 1 produces the source of truth that phase 4 (outline) will draw from. If a slide claim cannot be traced back to a phase 1 file, the slide is wrong.

## Sub-tasks

| # | Sub-task | Tool | Success criteria |
|---|----------|------|------------------|
| 1.1 | Codebase feature inventory | Glob + Grep + Read | Every backend module + frontend component listed |
| 1.2 | Architecture summary (modules + integrations) | Read CLAUDE.md, .claude/rules/project-structure.md, _alire/01_DOCUMENTATION/architecture/*.md | architecture_summary.md complete |
| 1.3 | Real metrics with verifiable commands | Bash | metrics.md table populated, every line has a command |
| 1.4 | Product website doc fetch (if applicable) | WebFetch | Raw HTML cached in sources_raw/, parsed into platform/website_facts.md |
| 1.5 | Screenshot capture via Playwright | webapp-testing skill | At least 8 screenshots covering the main personas |
| 1.6 | Cross-reference: every feature in inventory has a code anchor | Grep | features_inventory.md ends with anchor refs |
| 1.7 | Present G2 Discovery gate to user | conversation | User confirms inventory matches reality |

## Metrics catalogue (LIA-SEC example, ADAPT to product)

For LIA-SEC specifically, metrics.md should at minimum contain:

| Metric | Verification command |
|--------|---------------------|
| Backend Go API routes | `grep -rh "HandleFunc\|RegisterRoutes" cmd/sigma_web/*.go \| grep -oP '"/api[^"]*"' \| sort -u \| wc -l` |
| Backend Go .go files | `find cmd/sigma_web -maxdepth 1 -name "*.go" -not -name "*_test.go" \| wc -l` |
| Backend binary size | `ls -lh cmd/sigma_web/sigma_web_backend \| awk '{print $5}'` |
| React .tsx components | `find sigma-react-frontend/src/components -name "*.tsx" \| wc -l` |
| React services | `find sigma-react-frontend/src/services -name "*.ts" \| wc -l` |
| PostgreSQL tables | `PGPASSWORD=$LIA_DB_PASS psql -h localhost -U lia_admin -d lia_scan -t -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"` |
| CVE rows | `PGPASSWORD=$LIA_DB_PASS psql -h localhost -U lia_admin -d lia_scan -t -c "SELECT count(*) FROM cve_nvd_data"` |
| KEV rows | `PGPASSWORD=$LIA_DB_PASS psql -h localhost -U lia_admin -d lia_scan -t -c "SELECT count(*) FROM cisa_kev"` |
| Sigma rules | `find lia_rules/rule_analysis -name "*.yml" \| wc -l` |
| AI providers configured | `PGPASSWORD=$LIA_DB_PASS psql -h localhost -U lia_admin -d lia_scan -t -c "SELECT count(*) FROM ai_providers WHERE enabled=true"` |
| Compliance frameworks | List from `lia_rules/rule_analysis/COMPLIANCE/` |
| Discovery scan engines | `find cmd/sigma_web -name "discovery_*.go" \| wc -l` |

For other products, build the equivalent table from the actual code structure.

**Forbidden:** copying numbers from CLAUDE.md / memory / previous PLAN files. Always re-run the command.

## Features inventory structure

```markdown
# Features Inventory -- {PRODUCT}

Date verified : {YYYY-MM-DD}

## Module : {module name}

| Feature | Description | Code anchor | Status |
|---------|-------------|-------------|--------|
| ... | ... | cmd/sigma_web/{file}.go:{line} | shipped / beta / planned |

## Module : ...
```

Every row needs a code anchor. No anchor = no entry.

## Screenshot plan (LIA-SEC example, adapt)

The 8 minimum screenshots should cover:
1. CISO overview dashboard (macro view)
2. CVE Explorer with attack chain
3. Discovery Lab (scan results)
4. SMSI / GRC dashboard
5. NIS2 / compliance score
6. Rule authoring UI (admin power)
7. Remediation tracking kanban
8. AI agentic action (provider switch / prompt template)

For LIA-SEC the URL is `https://liascan.tech` (production VPS). Ask the user for credentials if needed.

Use the `webapp-testing` skill (Playwright). DO NOT navigate manually with mcp__playwright__* unless the skill instructs you to.

## G2 Discovery gate -- exact wording to send to user

```
G2 DISCOVERY VALIDATION

I have inventoried the product:

- {N} backend routes verified
- {N} React components verified
- {N} PostgreSQL tables verified
- {N} screenshots captured: {list}
- {N} modules documented in features_inventory.md

Top facts I plan to bring into the deck:
1. {fact 1 with metric}
2. {fact 2 with metric}
3. {fact 3 with metric}

Please skim platform/features_inventory.md and platform/metrics.md.

Anything missing? Anything overstated? Reply "valide" to proceed to phase 2 RESEARCH.
```

NEVER auto-progress past G2.

## Anti-patterns in this phase

- Quoting a metric without re-running the command
- Listing a feature you have not actually grepped for
- Using marketing words ("powerful", "revolutionary", "next-gen") -- this phase is purely factual
- Skipping screenshots ("the user knows the product")
- Cherry-picking modules to make the product sound bigger
