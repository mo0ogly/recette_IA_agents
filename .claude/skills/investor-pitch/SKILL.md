---
name: investor-pitch
description: End-to-end orchestration of investor pitch deck creation (PowerPoint .pptx) backed by REAL research with NO invention. Resumable across sessions via persistent tracking. Use when the user asks to "build an investor pitch", "investor deck", "pitch deck", "fundraising deck", "deck investisseur", "pitch investisseur", "presentation pour levee de fonds", "demarcher des investisseurs", "preparer un pitch VC", or any equivalent. The skill is product-agnostic (parameterized by product name) and runs a 6-phase agentic loop (INIT then DISCOVERY then RESEARCH then POSITIONING then OUTLINE then BUILD then REVIEW), with mandatory user checkpoints, source-cited research, and a claims-audit gate before delivery. Do NOT use for internal status reports (use internal-comms), sales decks (use pptx directly), or generic presentations.
---

# Investor Pitch -- Agentic Pitch Deck Builder

> **Mission:** Produce an investor-grade pitch deck in which every claim has a source. No invention, no marketing fluff, no hallucinated metrics. Resumable across sessions.

This skill is the orchestrator. It does NOT generate slides directly. It runs the methodology, calls other skills (`pptx`, `webapp-testing`, `doc-coauthoring`, `brand-guidelines`, `theme-factory`) and agents (`websearch-agent`) at the right phase, and enforces tracking discipline so any future session can resume cleanly.

---

## Agentic Loop (CORE PROTOCOL -- always follow)

```
OBJECTIVE -> DECOMPOSE -> PLAN -> ACT -> OBSERVE -> EVALUATE -> (REPLAN if needed) -> LOOP or COMPLETE
```

You are a goal-directed autonomous agent. You do NOT answer pitch questions directly. You decompose the deck-building objective into sub-tasks, execute them via dedicated tools, observe results, and adapt. Every action is logged.

| Phase | Action |
|-------|--------|
| 1 DECOMPOSE | Break the objective into 3-7 discrete sub-tasks. Identify dependencies. Estimate complexity TRIVIAL / MODERATE / COMPLEX. Output the decomposition before proceeding. |
| 2 PLAN | For each sub-task: state the goal, select tools and justify, define expected output, define success criteria and failure signal. |
| 3 ACT | Execute one tool at a time (parallel only if independent). Never guess parameters. Capture full result. |
| 4 OBSERVE | State what happened (factual). Compare actual vs expected. Classify SUCCESS / PARTIAL / FAILURE. |
| 5 EVALUATE | SUCCESS -> next sub-task. PARTIAL -> retry with adjustment or accept. FAILURE -> trigger REPLAN. |
| 6 REPLAN | Diagnose failure. Generate >= 2 alternatives. Select best with reasoning. Update plan. Log decision. NEVER retry the exact same action. |

**Hard constraints:**
- Never skip a phase
- Never hallucinate tool capabilities
- Never retry a failed action identically
- Never proceed without logging
- Escalate to user after 3 failed replanning attempts on the same step
- Prefer reversible actions over irreversible ones
- When in doubt, ask -- do not assume

---

## Decomposition des sous-taches (C1)

At skill activation, decompose into the 6 product phases. Each phase is itself decomposed into 3-7 sub-tasks at runtime. The 6 phases are NEVER skipped, NEVER reordered.

| # | Phase | Owner skill/agent | Output | Complexity | Depends on |
|---|-------|------------------|--------|------------|-----------|
| 0 | **INIT** -- scope intake + working dir setup | this skill | working dir, PLAN.md, decision_log.jsonl, README.md | MODERATE | nothing |
| 1 | **DISCOVERY** -- factual product inventory | this skill + webapp-testing + Read/Grep | platform/features_inventory.md, platform/metrics.md, platform/screenshots/ | COMPLEX | phase 0 |
| 2 | **RESEARCH** -- market, competitors, pricing, regs | websearch-agent | research/competitors.md, market_sizing.md, pricing_benchmarks.md, regulatory_drivers.md | COMPLEX | phase 0 |
| 3 | **POSITIONING** -- narrative, USP, moat, roadmap, ask | this skill (+ doc-coauthoring optional) | positioning/*.md | MODERATE | phases 1, 2 |
| 4 | **OUTLINE** -- 20-slide structure with sources | this skill | deliverables/deck_outline.md | MODERATE | phase 3 |
| 5 | **BUILD** -- generate the .pptx | pptx skill (+ brand-guidelines / theme-factory optional) | deliverables/pitch_v1.pptx + speaker_notes.md | COMPLEX | phase 4 USER VALIDATED |
| 6 | **REVIEW** -- claims audit | this skill | deliverables/claims_audit.md | MODERATE | phase 5 |

Phases 1 and 2 can be parallelized (independent). Phase 3 depends on both. Phase 4 must be USER-VALIDATED before phase 5 starts.

Detailed sub-tasks per phase: see `references/phase0-init.md` ... `references/phase6-review.md`.

---

## Plan d'execution (C2)

Before any action, create the persistent plan:

```bash
PRODUCT_SLUG="lia-sec"   # parameterized: ask the user, default to product name slug
DATE=$(date +%Y-%m-%d)
PITCH_DIR="_alire/tracking/investor_pitch_${PRODUCT_SLUG}_${DATE}"
mkdir -p "${PITCH_DIR}"/{research,platform/screenshots,positioning,deliverables,sources_raw}
```

Then write `${PITCH_DIR}/PLAN.md` from the template (see `references/working-directory.md` for the full layout and template).

The PLAN.md tracks:
- Phase checkboxes (0..6)
- Current phase + next action
- User checkpoints reached / pending
- Open blockers
- Working memory (completed / current / pending sub-tasks, key findings)

Update PLAN.md at every phase transition. On completion: Status -> TERMINE + Resultat.

If interrupted: any future session can resume by reading `${PITCH_DIR}/README.md` first, then PLAN.md.

---

## Adaptation et replanification (C3)

| Trigger | Action |
|---------|--------|
| 1 sub-task fails | Retry once with adjusted parameters |
| 2 consecutive failures on same sub-task | STOP -> invoke `/replan` -> NEVER improvise |
| User invalidates phase 4 outline | Loop back to phase 3, NOT to a partial fix |
| Web research returns unsourced claim | Reject the source, log rejection, find another |
| Phase 5 build fails | Retry once with simplified outline -> if fails, STOP and ask user |
| 3 failed replans on same sub-task | STOP -> escalate to user with full diagnosis |

`/replan` produces `${PITCH_DIR}/PLAN_REPLAN_{N}.md` linked from PLAN.md. Log `action="REPLAN_TRIGGERED"` in decision_log.jsonl.

**REPLAN format (mandatory):**

```markdown
### Replan - Phase {N} - Sub-task {X}
Failure cause: {wrong tool / wrong assumption / missing data / external error}
Alternatives considered:
  A. {approach A} -- rejected because {reason}
  B. {approach B} -- selected because {reason}
  C. {approach C} -- fallback if B fails
New plan: {updated steps}
```

**Critical rule:** Never retry exactly the same action. Change at least one parameter (tool, approach, data source, scope).

---

## Outils declares (C4)

| Tool | When to use |
|------|-------------|
| Read | Read a known file (path is exact) |
| Glob | Find files by pattern (path unknown) |
| Grep | Search content across many files (avoid N Reads) |
| Edit | Modify existing file (preferred over Write) |
| Write | Create new file or full rewrite |
| Bash | Run commands (build, mkdir, python scripts, git) |
| WebFetch | Fetch a known URL (e.g. liascan.tech doc page) |
| **websearch-agent** (Agent tool) | ALL web research in phase 2. NEVER call WebSearch directly -- the agent isolates noise and produces sourced reports |
| **pptx skill** (Skill tool) | Phase 5 only -- deck generation from validated outline |
| **webapp-testing skill** (Skill tool) | Phase 1 -- Playwright screenshots of the product website |
| **doc-coauthoring skill** (Skill tool) | Phase 3 OPTIONAL -- structured narrative drafting |
| **brand-guidelines / theme-factory** (Skill tool) | Phase 5 OPTIONAL -- visual styling |
| **frontend-design / canvas-design** (Skill tool) | Phase 5 OPTIONAL -- custom slide visuals |
| **/replan** (Skill tool) | On 2 consecutive sub-task failures |
| **TaskCreate** | Track sub-tasks per phase (visible to user) |

**Selection criteria (dynamic):**

- Web research -> ALWAYS websearch-agent (never WebSearch direct)
- Reading source code metric -> Bash (`grep -c`, `find | wc -l`, `psql -c`)
- Reading a doc URL we already know -> WebFetch
- Reading multiple unknown files -> Glob then Read
- Capturing UI screenshot -> webapp-testing (Playwright)
- Generating .pptx -> pptx skill (NEVER reimplement)

**Retry policy:** 1 retry with adjusted parameters -> if 2nd failure -> log decision_log.jsonl + invoke /replan + signal user.

---

## Tracabilite agentique (C5)

### Decision log

Append to `_alire/02_LOGS/Journals/decision_log.jsonl` for every non-trivial choice. Examples of trivial (DO NOT log): file read, build run, formatting. Examples of non-trivial (DO log): pivot in narrative, change of competitor list, rejection of a source, scope change, replan.

```bash
echo '{"timestamp":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","session":"investor-pitch","action":"PHASE_X_DECISION","reasoning":"...","alternatives_rejected":["..."],"outcome":"...","confidence":"high|medium|low","plan_ref":"'${PITCH_DIR}'/PLAN.md"}' >> _alire/02_LOGS/Journals/decision_log.jsonl
```

### Web research log

Every single web fetch / search must be logged in `${PITCH_DIR}/research/web_research_log.md`:

```markdown
| Date       | Query                              | URL                              | Source kind | Takeaway (1 line)               | Used in slide |
|------------|------------------------------------|----------------------------------|-------------|---------------------------------|---------------|
| 2026-04-11 | "Wiz cloud security platform price"| https://wiz.io/pricing           | vendor      | No public pricing, contact sales| 12            |
```

### Metrics log

Every internal product metric (route count, table count, CVE count, etc.) must be logged in `${PITCH_DIR}/platform/metrics.md` with the EXACT command used:

```markdown
| Metric             | Value   | Command (verifiable)                                                            | Date       |
|--------------------|---------|---------------------------------------------------------------------------------|------------|
| Go API routes      | 562     | `grep -rh "HandleFunc\|RegisterRoutes" cmd/sigma_web/*.go | wc -l`              | 2026-04-11 |
| PostgreSQL tables  | 268     | `PGPASSWORD=$LIA_DB_PASS psql -h localhost -U lia_admin -d lia_scan -t -c "..."`| 2026-04-11 |
```

NEVER quote a metric without its source command. NEVER copy a number from CLAUDE.md without re-verifying.

### RETEX

At end of session (or end of phase 6), produce `_alire/02_LOGS/Journals/retex/RETEX_INVESTOR_PITCH_${DATE}.md`. ALWAYS, not only on low score. Investor pitch is a high-stakes deliverable -- the RETEX serves the next iteration.

---

## VERIFICATION GATE (BLOQUANT)

Before declaring the skill done, ALL of these must pass:

- [ ] Working directory exists at `_alire/tracking/investor_pitch_*/`
- [ ] PLAN.md status = TERMINE, all 7 phases checked
- [ ] decision_log.jsonl has at least one entry per phase 2-5
- [ ] research/web_research_log.md is non-empty AND every entry has a URL
- [ ] platform/metrics.md is non-empty AND every metric has a verifiable command
- [ ] deliverables/deck_outline.md is USER-VALIDATED (mark explicitly)
- [ ] deliverables/pitch_v1.pptx exists and opens (`unzip -l` returns slide entries)
- [ ] deliverables/claims_audit.md exists -- every slide claim cross-referenced to a source file
- [ ] Zero unsourced number in the final deck
- [ ] RETEX written
- [ ] Librarian Gate done: PLAN copied to canonical tracking, INDEX.md updated, commit groups all artifacts

If any gate fails: STOP, fix, re-gate. NEVER declare "done" with a red gate.

---

## The 6 Phases (high-level) -- read the matching reference file before starting each

| Phase | Reference file | Read BEFORE entering this phase |
|-------|----------------|--------------------------------|
| 0 INIT | `references/phase0-init.md` | Scope intake questions, working dir setup, PLAN bootstrap |
| 1 DISCOVERY | `references/phase1-discovery.md` | Codebase inventory, real metrics, screenshots |
| 2 RESEARCH | `references/phase2-research.md` | websearch-agent briefs, source taxonomy, source rejection rules |
| 3 POSITIONING | `references/phase3-positioning.md` | Narrative templates, USP framework, ask formula |
| 4 OUTLINE | `references/phase4-outline.md` | 20-slide canonical structure, slide-content contract |
| 5 BUILD | `references/phase5-build.md` | pptx skill invocation, theme selection, screenshot embedding |
| 6 REVIEW | `references/phase6-review.md` | Claims audit checklist, source cross-reference, librarian gate |

Working directory layout: `references/working-directory.md`
Anti-patterns to refuse: `references/anti-patterns.md`

---

## User checkpoints (BLOCKING)

The user is the loop closer. The skill MUST stop and wait for explicit user validation at these gates:

| Gate | After phase | What the user validates |
|------|-------------|------------------------|
| G1 Scope | 0 | Audience, round size, geo, slide count, competitors list, pricing strategy assumptions |
| G2 Discovery | 1 | The factual inventory matches reality (no missing module, no overstated metric) |
| G3 Research | 2 | The competitor set and market sizing assumptions are valid |
| G4 Outline | 4 | The 20-slide structure is the contract for the deck. NO .pptx generation before validation |
| G5 Final | 6 | Claims audit reviewed, deck approved for delivery |

NEVER skip a gate. NEVER auto-progress past a gate without explicit user "OK / valide / go".

---

## Anti-patterns (instant FAIL)

- Generating slides before phase 4 outline is user-validated
- Quoting any market number, competitor fact, or pricing benchmark without a source URL in the same line
- Reusing a number from `CLAUDE.md` or memory without re-running its source command
- Skipping screenshot capture because "the website is enough"
- Calling WebSearch directly instead of websearch-agent
- Treating the product as LIA-SEC by default -- the skill MUST be parameterized
- Forgetting to create PLAN.md and decision_log.jsonl in phase 0
- Inventing competitor pricing because "they probably charge X" -- if no public pricing, write "no public pricing, contact sales"
- Padding the deck with vision slides when the data isn't there
- Producing a deck that contradicts the codebase metrics

Full list and rationale: `references/anti-patterns.md`.

---

## Scoring agentique

| Critere | Score |
|---------|-------|
| C1 Decomposition : 6 phases + sub-tasks identified per phase | /10 |
| C2 Planification : PLAN.md created in phase 0, updated each phase, closed | /10 |
| C3 Replanification : /replan triggered on 2+ failures, NEVER improvised | /10 |
| C4 Outillage : websearch-agent for web, pptx for build, no shortcut | /10 |
| C5 Tracabilite : decision_log + web_research_log + metrics_log + RETEX | /10 |

Score total : /50 -- >= 40 Exemplaire | 30-39 Acceptable | < 30 RETEX MANDATORY with corrective actions

Investor pitch is high-stakes -- target >= 45/50.
