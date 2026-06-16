# OODA Protocol -- Documentation Generation Loop

Adapted from the Autonomous Agentic Agent system prompt for doc-code.
The Program Director follows this loop for every documentation objective.

---

## The Loop

```
OBJECTIVE -> OBSERVE -> ORIENT -> DECIDE -> ACT -> OBSERVE -> ... -> COMPLETE
```

Each phase is mandatory. Never skip a phase.

---

## Phase 1: OBSERVE (Gather Facts)

**Goal:** Build a factual picture of the current state before any action.

**Actions:**
1. **Inventory existing docs** for the target module:
   ```bash
   # Find all docs related to the module
   find _alire/01_DOCUMENTATION/ -name "*{module}*" -type f 2>/dev/null
   # Check metadata
   python3 .claude/skills/doc-code/scripts/doc_classifier.py list _alire/01_DOCUMENTATION/
   ```
2. **Read the code** -- NEVER generate docs from memory or assumptions:
   - Glob the target files
   - Read each file
   - Grep for exported symbols
3. **Check doc freshness** -- compare doc version date vs last code modification:
   ```bash
   git log --oneline -5 -- {code_files}
   # Compare with doc-meta.json "updated" field
   ```
4. **Identify stakeholders** -- who will read this doc? (dev, RSSI, auditor)

**Output format:**
```
## OBSERVE -- {module}

Existing docs: {list with paths, versions, dates}
Code files in scope: {count} files, {LOC} lines
Last code change: {date, commit}
Last doc update: {date, version} or "NO EXISTING DOC"
Freshness: CURRENT | STALE | MISSING
Stakeholders: {audience}
```

---

## Phase 2: ORIENT (Analyze & Contextualize)

**Goal:** Understand what needs to happen based on observations.

**Decision matrix:**

| Situation | Action |
|-----------|--------|
| No existing doc | CREATE: full template, all agents |
| Doc exists, code unchanged | SKIP: no action needed |
| Doc exists, code changed (minor) | UPDATE: bump PATCH, update changed sections only |
| Doc exists, code changed (major) | UPDATE: bump MINOR/MAJOR, re-run relevant agents |
| Doc exists, code deleted/moved | ARCHIVE: move to _alire/01_DOCUMENTATION/archive/, create new if relocated |
| Doc exists, contradicts code | FIX: flag as ANOMALY, correct doc, bump version |

**Complexity assessment:**

| Factor | Score | Criteria |
|--------|-------|----------|
| File count | +1 per 5 files | Number of files in scope |
| Handler count | +1 per 3 handlers | API endpoints to document |
| Component count | +1 per 5 components | React components |
| Table count | +1 per 3 tables | PostgreSQL tables |
| Cross-cutting | +3 | Module spans backend + frontend |
| Security-sensitive | +2 | Auth, crypto, input validation |

- Score 1-3: TRIVIAL -- single agent (Backend OR Frontend), no Architect
- Score 4-7: MODERATE -- full swarm minus optional roles
- Score 8+: COMPLEX -- full swarm, all roles, QA mandatory

**Output format:**
```
## ORIENT -- {module}

Action: CREATE | UPDATE | ARCHIVE | SKIP | FIX
Complexity: TRIVIAL ({score}) | MODERATE ({score}) | COMPLEX ({score})
Agents needed: {list of roles to launch}
Agents skipped: {list with reason}
Estimated sections: {count}
Risk factors: {what could go wrong}
```

---

## Phase 3: DECIDE (Plan of Action)

**Goal:** Commit to a specific plan before executing.

**Plan structure:**
```
## DECIDE -- {module}

Plan:
1. [Phase 1] Launch {agents} in parallel
2. [Phase 2] Collect reports, launch Architect
3. [Phase 3] Write/update docs using template
4. [Phase 4] Launch QA
5. [Phase 5] Launch Recette
6. [Gate] QA score >= 80 to proceed
7. [Final] Archive old version, commit new docs

Success criteria: {measurable checks}
Failure signal: {what triggers replanning}
Rollback: {how to undo}
```

**Replanning trigger:** If 2+ agents fail OR QA score < 60, REPLAN:
1. Diagnose WHY (wrong scope, missing code access, timeout)
2. Generate 2 alternatives (reduce scope, retry with different params, manual fallback)
3. Select best alternative with reasoning
4. Log in decision_log.jsonl

---

## Phase 4: ACT (Execute the Plan)

**Goal:** Execute step by step, logging each action.

**Rules:**
- Launch independent agents in parallel (1 message, N tool calls)
- Sequential agents wait for dependencies
- After each agent completes: validate output format, check for ANOMALIES section
- Write docs using the standard template (references/doc-template-standard.md)
- Every file written gets metadata initialized via doc_classifier.py

**Journal format (append-only):**
```
[{ISO8601}] PHASE=ACT STEP={N} ACTION={verb} AGENT={role} INPUT={summary} OUTPUT={summary} STATUS={success|partial|failure} ANOMALIES={count}
```

---

## Phase 5: OBSERVE (Post-Action Verification)

**Goal:** Verify what actually happened vs what was planned.

**Checks:**
1. All planned docs exist on disk
2. Metadata initialized for each doc
3. Diagrams generated (.json + .mmd)
4. QA score meets threshold (>= 80)
5. Anomalies cataloged in Recette report
6. No regression in existing docs (other modules untouched)

**Output format:**
```
## POST-OBSERVE -- {module}

Docs created: {count} ({paths})
Docs updated: {count} ({paths})
Docs archived: {count} ({paths})
Diagrams: {count} ({types})
QA score: {XX}/100
Anomalies found: {count} ({severity breakdown})
Plan adherence: {match % vs DECIDE phase}
```

---

## Completion Protocol

When all phases complete:

```
## COMPLETION -- {module}

Objective: {original objective}
Status: ACHIEVED | PARTIALLY_ACHIEVED | FAILED
Results:
  1. Docs: {list with versions}
  2. Diagrams: {list}
  3. QA: {score}/100
  4. Anomalies: {count} surfaced to RETEX
Duration: {phases completed}
Next steps: {suggestions}
```

---

## Constraints

1. Never skip a phase -- every action goes through OBSERVE -> ORIENT -> DECIDE -> ACT
2. Never generate docs from memory -- always READ the code first
3. Never retry a failed action identically -- always change at least one variable
4. If stuck after 3 replanning attempts, escalate to user
5. Always prefer reversible actions (archive > delete)
6. Journal is mandatory and append-only
