---
name: apex
description: APEX v6.0 -- Autonomous agentic loop level 6. OODA-integrated cycle INIT -> OBSERVE -> THINK -> BUILD -> RECETTE -> COMPLETE. 3-level memory. Research phase with adversarial critique. Rust/React build pipelines. 4-step blocking recette. Swarm inter-agent memory. Self-learning. Escalation only when autonomy boundary exceeded. Triggers on "apex", "plan d'attaque", "implemente cette feature", "workflow structure".
---

# APEX v6.0 -- Autonomous Agentic Loop

Architecture level 6: the agent observes, thinks, builds, validates, and loops -- autonomously, until the objective is met or a decision exceeds its autonomy perimeter.

## Core: the loop

```
INIT -> OBSERVE -> THINK -> BUILD (OODA per subtask) -> RECETTE -> COMPLETE
  ^                                                                    |
  |________________ LEARNING (RETEX + long-term memory) _______________|
```

**This is NOT a sequential pipeline.** It is a running process. Each action is followed by observation and evaluation. The loop stops only on:
- COMPLETE: objective achieved (all success criteria validated)
- ESCALADE: decision outside autonomy perimeter
- ABORT: 3 consecutive failures on the same subtask after REPLAN

---

## Syntax

```
/apex [flags] <task description>
```

| Flag | Description |
|------|-------------|
| `--swarms` | Parallel delegation to subagents |
| `--research` | Enable web search in THINK phase |
| `-x` / `--examine` | Adversarial review after each batch |
| `-t` / `--test` | Include test creation + execution |
| `-b` / `--branch` | Create a feat/ branch |
| `-pr` / `--pull-request` | Create a PR at the end |
| `-d` / `--deploy` | Run Phase 4f DEPLOY (build + push to prod via `./deploy.sh`) after RECETTE passes. Requires explicit user GO at the gate (deploy is an autonomy-boundary action). |
| `-e` / `--economy` | No subagents |
| `-r <id>` / `--resume <id>` | Resume from a previous session |

**Default: AUTONOMOUS.** No confirmation between steps. Escalation only when necessary.

---

## Shared References

APEX v6.0 delegates protocol details to shared reference files. Read these BEFORE executing:

| Reference | Content |
|-----------|---------|
| [_shared/references/agentic-core.md](../_shared/references/agentic-core.md) | Memory 3 levels, autonomy perimeter, model selection, pre-flight, scoring /50 |
| [_shared/references/swarm-memory-protocol.md](../_shared/references/swarm-memory-protocol.md) | swarm_memory.json schema, lifecycle, merge protocol |
| [_shared/references/build-pipeline-rust.md](../_shared/references/build-pipeline-rust.md) | Rust build pipeline (5 sequential steps per .rs file) -- imposes rust-best-practices + error-handling-patterns skills |
| [_shared/references/build-pipeline-python.md](../_shared/references/build-pipeline-python.md) | Python build pipeline (ruff + mypy + bandit + pip-audit + pytest) -- secondary backend language |
| [_shared/references/build-pipeline-react.md](../_shared/references/build-pipeline-react.md) | React build pipeline (8 gates per .tsx/.ts file) |
| [_shared/references/recette-protocol.md](../_shared/references/recette-protocol.md) | 4-step blocking recette (static, runtime, contract, regression) |
| [_shared/references/librarian-gate.md](../_shared/references/librarian-gate.md) | Blocking end-of-cycle checklist |
| [_shared/references/retex-protocol.md](../_shared/references/retex-protocol.md) | RETEX + DASHBOARD templates, scoring criteria |
| [_shared/references/agent-delegation.md](../_shared/references/agent-delegation.md) | Delegation format, roles, quality hooks, OODA security |
| [references/action-journal-spec.md](references/action-journal-spec.md) | Action journal, staging protocol, manifeste JSONL, FILE_TRACKER v2 |
| [references/agent-delegation-protocol.md](references/agent-delegation-protocol.md) | APEX-specific delegation protocol (legacy, complements _shared) |
| [references/quality-hooks.md](references/quality-hooks.md) | QH-A1..A5, OODA security layer, context management |

---

## Phase 0 : INIT (Pre-flight + Resume)

**0a. MANDATORY first step (DEFAULT-ON, c40 A50 + c41 A57 bake-in)** -- source
the apex_init wrapper which (i) exports `APEX_DEV_ROOT`/`APEX_LOGS_ROOT`/
`APEX_TEMP_ROOT`, (ii) sources `journal_helpers.sh`, (iii) initializes the
session, (iv) emits the canonical INIT entry. One line:

```bash
source /opt/inspect_ia_agents/dev/scripts/apex_init.sh "apex-{YYYYMMDD}-{slug}" "session start; task=<description>"
```

Closes the c37/c38 gap where `decision_log.jsonl` stayed empty because the
helper had to be sourced manually and was forgotten. With apex_init, the
helpers are available the moment the cycle's first Bash call lands.

After this, every REPLAN MUST use `apex_log_replan` (writes BOTH action_journal
AND decision_log atomically) and every SELECT_ALTERNATIVE in Phase 2 MUST use
`apex_log_decision`. Self-tests:
- `bash scripts/journal_helpers.sh selftest`
- `bash -c 'source scripts/apex_init.sh selftest-id "selftest"'` (subshell)

**0b. Historical traceability scan (c54+, WARN-not-BLOCK)** -- detect missing
PLAN/RETEX pairs in PRIOR cycles of the active PDCA scope BEFORE the new
cycle starts. Surfaces eroded discipline early so it can be backfilled or
acknowledged in this cycle's PLAN.

```bash
python3 /opt/inspect_ia_agents/dev/scripts/verify_cycle_traceability.py \
    --scope {SCOPE_SLUG} \
    --to-cycle {N-1}
```

Where `{SCOPE_SLUG}` is the upper-snake-case PDCA scope
(e.g. `RECETTE_CORPUS`, `DISCOVERY_RECETTE`).

Exit code interpretation at Phase 0:
- 0 = clean, proceed
- 1 = PARTIAL (PLAN xor RETEX missing on some prior cycle) -> log a WARN in
  PLAN's pre-flight section, proceed
- 2 = CONSECUTIVE GAP detected on prior cycles -> WARN + add a "Traceability
  debt" entry to PLAN's pre-flight section listing the gap range. If a
  `TRACEABILITY_GAP_{slug}_{range}_{DATE}.md` document already exists for
  this range, mark as ACKNOWLEDGED. Otherwise queue an A100-style backfill
  task in this cycle's queue.

NOT BLOCKING at Phase 0 (some legitimate cycles like retex-analyzer or
audit-only scopes may intentionally lack PLAN files). Phase 5 librarian-gate
enforces the CURRENT cycle's PLAN+RETEX presence as BLOCKING.

Reference incident : a multi-cycle marathon session ran without PLAN/RETEX.
Forensic reconstruction via audit-block grep proved work happened but the
trace was lost -- hence the mandatory traceability gate.
c54 bakes this preventive scan to prevent recurrence.

1. **Parse** the task description: identify domain (backend Rust, backend Python, frontend React, rules, infra, mixed)
2. **Resume check** (`-r <id>` flag):
   - If resume: load `docs/tracking/apex/{id}/FILE_TRACKER.json`, resume from last incomplete subtask
   - If fresh: generate session id `apex-{YYYYMMDD}-{slug}` and feed it to `apex_journal_init`
3. **Create PLAN immediately**: `docs/tracking/PLAN_APEX_{slug}_{date}.md` (template from agentic-core.md)
4. **Pre-flight** (BLOCKING):
   - Rust: `cargo build 2>&1 | tail -20` (must compile; `-p <crate>` if multi-crate workspace)
   - React: `cd console && node node_modules/.bin/vite build 2>&1 | tail -5` (must pass)
   - Backend health: `curl -s http://localhost:8081/api/health | head -1` (WARN only, not BLOCK)
5. **Test pre-flight** (WARN, not BLOCK):
   - `cargo test --no-run 2>&1 | tail -5` then `cargo test 2>&1 | grep -cE 'FAILED|test result: FAILED'` -- note pre-existing failures for regression baseline
6. **Initialize session artifacts** in `docs/tracking/apex/{session-id}/`:
   - `action_journal.jsonl` (empty)
   - `FILE_TRACKER.json` (empty)
   - `swarm_memory.json` (if `--swarms`, see swarm-memory-protocol.md)

**Tracking is gitignored work-memory (R25 -- BLOCKING).** Every APEX artifact (session dir,
journals, FILE_TRACKER, swarm_memory, PLAN, RETEX, decision_log) lives under `docs/tracking/`,
which is gitignored. This repo is a ground-truth corpus; committing APEX work-trace pollutes it.
NEVER write an APEX artifact at the repo root, NEVER `git add` anything under `docs/tracking/`.
Durable deliverables (product doc, runbook) go in committed `docs/`, not `docs/tracking/`.

Gate: pre-flight MUST pass. If failure and the task is NOT to fix the pre-requisite -> STOP.

---

## Phase 1 : OBSERVE (Cartography + Health Scan)

**OODA: Observe + Orient**

1. **Collect data**: read relevant files, map dependencies, check git status
2. **Load previous RETEX**: search `docs/tracking/retex/` for same-domain RETEX. Apply lessons learned. Do NOT repeat documented mistakes.
3. **Health scan** (MANDATORY, display results). Every grep appends the transverse exclusion
   set `-vE '/target/|/node_modules/|/dist/|/\.worktrees/|docs/tracking/|/pdca/|__pycache__|\.orig$|\.bak$'`
   -- a match only in a build artifact, vendored dep, worktree, or tracking file is a GHOST, not
   a finding (this repo guarantees all of those paths exist). Drop it, never score it.
   - Input validation: handler extractors without typed parse/validation (e.g. raw `String` path param without `Uuid`/`Ulid` parse)
   - Error-handling debt: `.unwrap()`/`.expect()`/`panic!` on fallible paths in non-test code (grep `-rn '\.unwrap()\|\.expect(\|panic!' src/ --include='*.rs'`)
   - Test coverage: `.rs` files > 200 LOC without a `#[cfg(test)]` mod or matching `tests/` file
   - Structural debt: files exceeding LOC limit without @allow-long-file
4. **Orient**: load relevant context
   - Documentation: `docs/` -- existing docs for this domain
   - Skills: CLAUDE.md rules, anti-patterns
   - Previous decision_log entries for this domain

Output: health scan results displayed. Context loaded for THINK phase.

---

## Phase 2 : THINK (Research + Alternatives + Plan + Critique)

**OODA: Orient + Decide -- NEW in v6.0**

This phase produces a structured, critiqued plan BEFORE any code is written.

### 2a. Research

- **Codebase search**: "Has someone already done this?" -- Grep/Glob for existing implementations, patterns, utilities that can be reused. Check `docs/` for existing specs.
- **Web search** (if `--research` flag): use WebSearch/WebFetch for recent technical references, security advisories, best practices. Cite sources.
- **Log all research** in action_journal.jsonl with action `RESEARCH_CODEBASE` or `RESEARCH_WEB`.

### 2b. Alternatives

Evaluate minimum **2 architectural approaches**. For each:

```
ALTERNATIVE {letter}
  Approach   : {description}
  Pros       : {benefits}
  Cons       : {drawbacks}
  Effort     : {SMALL | MEDIUM | LARGE}
  Risk       : {LOW | MEDIUM | HIGH}
  Files      : {list of files to create/modify}
```

Log the selected alternative and rejected ones in `decision_log.jsonl`:
```json
{"timestamp":"ISO","session":"apex-{id}","action":"SELECT_ALTERNATIVE","reasoning":"A selected because...","alternatives_rejected":["B rejected because..."],"confidence":"high|medium|low"}
```

### 2c. Structured Plan

Decompose the selected alternative into **3 to 7 subtasks**. For each:

```
SUBTASK {N}/{total}
  Description  : {what}
  Files        : {which}
  Complexity   : TRIVIAL | MODERATE | COMPLEX
  Autonomy     : AUTONOMOUS | SUPERVISED (forced if: DDL, auth, irreversible, >5 files)
  Dependencies : {prerequisite subtasks}
  Tools        : {Read/Edit/Write/Bash/Agent}
  Success      : {measurable criterion}
  Failure      : {signal to trigger REPLAN}
  Rollback     : {how to revert}
  Pipeline     : RUST | PYTHON | REACT | MIXED | NONE
```

**Decomposition constraints:**
- 1 subtask = 1 responsibility (SRP)
- Explicit dependencies (no coupled subtasks)
- Measurable success criteria (not "it works" but "build OK + 0 vet errors + test passes")

### 2d. Adversarial Critique

**Konrad-Kurze pre-load (BEFORE the critique agent fires).**
Check for a recent (< 24h) meta-cognitive directive that targets Malcador or both:
```bash
ls -t docs/tracking/directives/KD-*.json 2>/dev/null | head -1
```
If a directive exists with `primary_target` in {Malcador, both}, `injection.operation = ADD`, AND `risk_level = LOW`: include its `injection.payload` and `expected_impact` in the critique agent's input prompt. If it has `requires_approval: true` and is not yet APPROVED: surface it in the plan as "Pending Konrad directive" but do NOT auto-apply.
If APEX has REPLANned >= 2 times on the same subtask in this session, INVOKE `/konrad-kurze` via the Skill tool (model: **sonnet**) BEFORE 2d, with scope = current WAVE id. The directive that comes back feeds into 2d.

Launch an agent Plan (sonnet) to critique the plan BEFORE execution:

```
DELEGATION:
  role: PLANNER
  model: sonnet
  task: "Critique this implementation plan. Identify: missing edge cases, security risks (OWASP), inspect_ia_agents rule violations (R1-R17) and invariant breaches (I1-I6), integration risks, missing tests, and suggest improvements."
  input: {the full plan from 2c}
  expected_output: structured critique with severity per finding
```

Integrate feedback: adjust subtasks, add missing gates, address identified risks. Log changes in decision_log.jsonl.

### Swarm Context Sheet (MANDATORY if `--swarms`)

Before launching parallel agents, prepare a **Swarm Context Sheet** included in EVERY agent prompt:

1. **Parent behavior**: what the parent component already does (auto-refresh, error handling, data loading) so children do not duplicate
2. **UI patterns**: components used for error states (`<Alert severity="error">`), loading (`CircularProgress`), feedback (`Snackbar`), empty states -- for cross-tab consistency
3. **Mandatory checklist**: HelpButton (component+tabKey), borderRadius:1, fontFamily:'inherit', structured logger, no console.log
4. **Shared state contract**: which props come from parent, which callbacks are available, what the agent MUST NOT re-implement

### Swarm Memory (if `--swarms`)

Create `swarm_memory.json` following [swarm-memory-protocol.md](../_shared/references/swarm-memory-protocol.md). Each agent receives it in their prompt context. After all agents complete, merge discoveries, deduplicate findings, cross-reference results.

---

## Phase 3 : BUILD (OODA Loop per Subtask)

For each subtask, execute the complete OODA cycle:

### ACT (Decide + Act)

Execute the subtask. Rules:
- inspect_ia_agents conventions: R1-R17, invariants I1-I6, deny-by-default, no emoji (see project CLAUDE.md)
- Policy gates: NO STUB, NO DISABLE, USAGE TRIAGE
- **NO CONFABULATION**: never invent a finding, file path, symbol, or score -- every claim is backed by a command output. A claim of "X missing/absent" requires the verify command + its output attached, else mark it `A_VERIFIER`, never a real severity (applied R13).
- **NO MOCK in production paths, EXCEPT the declared legitimate mocks.** The recette is mock-first by design: `StubLlm`/`ReplayLlm` (deterministic replay I4), `LabForge` + `recette/lab/mock_server.py` (simulated lab :8082), `mock_local` servers, and `tests/`/`__fixtures__` fixtures are the corpus HARNESS, not violations -- NEVER flag them as mock-data (false positive against the repo's own architecture).
- 1 file at a time, gate after each file
- Log in `action_journal.jsonl`:
  ```json
  {"timestamp":"ISO","step":N,"action":"EDIT","file":"path","status":"pending","alternatives_if_fail":[]}
  ```

**Rust files**: follow [build-pipeline-rust.md](../_shared/references/build-pipeline-rust.md) after each .rs write.
BEFORE writing: invoke the `rust-best-practices` skill (idiomatic borrowing/ownership, clippy
lints, perf) and, for any fallible boundary, the `error-handling-patterns` skill (Result vs
panic, thiserror/anyhow, retry/circuit-breaker). Both are MANDATORY, not optional. Then:
1. `cargo build` (workspace-aware, `-p <crate>` if multi-crate) -- must compile
2. `cargo fmt --all -- --check` (0 diff)
3. `cargo clippy --all-targets --all-features -- -D warnings` (0 warnings, BLOCKING)
4. `/test-first` via Skill tool (create `#[cfg(test)] mod tests` or `tests/*.rs` BEFORE merge; `cargo test` green)
5. Convention check: no `.unwrap()`/`.expect()`/`panic!` on fallible paths, typed errors, `tracing` not `println!`

**Python files**: follow [build-pipeline-python.md](../_shared/references/build-pipeline-python.md) after each .py write.
BEFORE writing fallible paths, invoke the `error-handling-patterns` skill. Then (tools in `.venv-pyaudit/bin/`):
1. `ruff check {file}` (0 findings, incl. flake8-bandit S security rules)
2. `ruff format --check {file}` (0 diff)
3. `mypy {file or package}` (0 errors)
4. `bandit -q -r --severity-level medium {package}` (0 MEDIUM+)
5. `/test-first` via Skill tool (create `tests/test_*.py` BEFORE merge; `pytest` green)
Convention check: `logging` not `print`, no bare `except`, no `eval`/`exec`/`pickle.load`, typed hints.

**React files**: follow [build-pipeline-react.md](../_shared/references/build-pipeline-react.md) after each .tsx/.ts write:
0. R17 PRE-BUILD CONTRACT GATE (BLOQUANT, for any *Dashboard/*Tab/*Panel/*Status/*Editor that calls an API): BEFORE writing the first line of the component, capture the live payload with curl and save to `console/src/components/__fixtures__/{component}.fixture.json`. Then draft the render-and-assert test skeleton in `{component}.contract.test.tsx` asserting at least one expected DOM element. The service layer MUST unwrap `{success, data}` -> `.data` explicitly (see `.claude/rules/frontend-contract-gate.md`). Skipping this step = PHASE 3 FAILURE, return to ACT. Past incidents (component crash on undefined payload + dashboard contract drift requiring multiple correction passes) mandated this pre-build gate.
1. BUILD: `vite build` zero TS errors
2. IMPORT: fetch with base URL from config (R5, never hardcode the URL)
3. THEME: fontFamily:'inherit', no hardcoded hex, theme.palette.*
4. LOGGER: structured logger (R6, not console.log)
5. CHIP: borderRadius:1 on all Chip/badge
6. HELP (BLOQUANT): INSERT ui_help_content AVANT HelpButton, verify SELECT, FAIL si contenu absent
7. TEST: `/test-first` via Skill tool (runs the contract test from step 0 against the captured fixture)
8. RUNTIME CRASH: Playwright navigate + snapshot (zero Component Error)
9. INTEGRATION (BLOQUANT, new files only): Verify component is imported by at least 1 parent. `grep -rn "import.*ComponentName" src/ | grep -v "ComponentName.tsx" | wc -l` must be >= 1. A compiled but never-imported component is ORPHAN = FAIL. Incident 2026-04-13: 3 orphan components shipped.

### OBSERVE (Observe)

After EACH action, observe the result:
- Build gate: `cargo build` (Rust) / `vite build` (React)
- Lint gate: `cargo clippy --all-targets -- -D warnings` (Rust, 0 warnings) / TS errors 0 (React)
- Test gate: existing tests must not break
- Diff review: `git diff` -- no regressions
- **Runtime crash gate (MANDATORY if frontend modified)**: navigate to the modified page with Playwright and verify ZERO `Component Error`. Pattern:
  ```
  mcp__playwright__browser_navigate -> target page
  mcp__playwright__browser_snapshot -> search "Error" in snapshot
  ```
  If "Component Error" or "is not a function" or "Cannot read properties of" appears: **FAILURE immediate**, fix before continuing. Incident 2026-04-06: `.map()` on null causes crashes invisible at build but visible in prod.

### EVALUATE (Orient + formal classification)

Classify the result:

| Verdict | Definition | Next action |
|---------|-----------|-------------|
| **SUCCESS** | Success criterion validated, all gates green | Move to next subtask |
| **PARTIAL** | Incomplete result but progressing | Continue with minor adjustment |
| **FAILURE** | Red gate or criterion not met | -> REPLAN (mandatory) |

Update `action_journal.jsonl` with verdict:
```json
{"timestamp":"ISO","step":N,"action":"EDIT","file":"path","status":"SUCCESS|PARTIAL|FAILURE","gate_results":{"build":"PASS","vet":"PASS"}}
```

### REPLAN (never the same action twice)

Triggered on FAILURE. Procedure:

1. **Diagnose**: why the action failed (read error, verify hypotheses -- R18 applies)
2. **Generate 2+ alternatives**: at minimum two different approaches
3. **Select** with explicit justification in `decision_log.jsonl`:
   ```json
   {"timestamp":"ISO","session":"apex-{id}","action":"REPLAN","reasoning":"build fail because X","alternatives_rejected":["approach B rejected because Y"],"selected":"approach C because Z","confidence":"high|medium|low"}
   ```
   **HELPER (REQUIRED -- closes c37/c38 gap)**: Use `apex_log_replan` from
   `scripts/journal_helpers.sh`. It writes BOTH `action_journal.jsonl` AND
   `decision_log.jsonl` atomically so the decision_log cannot stay empty by
   accident:
   ```bash
   source /opt/inspect_ia_agents/dev/scripts/journal_helpers.sh
   apex_journal_init "apex-{session-id}"
   apex_log_replan "S1" "build fail because X" "approach C" \
     --alternatives "A:tried;B:rejected because Y" --confidence high
   ```
   Also available: `apex_log_action`, `apex_log_decision`,
   `apex_log_midcycle_ajout`. Self-test : `bash scripts/journal_helpers.sh selftest`.
4. **Execute** the selected alternative -> return to ACT

**Escalation**: 3 REPLAN on the same subtask -> STOP, escalate to user.

### Mid-cycle user feedback ajout (REACTIVE pattern, v6.0+)

A cycle is NOT a sealed plan. When the user observes mid-cycle ("X is too many", "this looks wrong", "did you consider Y?"), evaluate inline whether the response fits the current cycle's scope or must be deferred to N+1.

**Acceptance criteria for inline ajout (ALL required):**
- The observation is **directly downstream** of a subtask already in flight (not a tangential new feature).
- The response can be implemented with the **same tool surface** already in use (no new build pipeline, no new skill scaffold).
- The work fits in **< 30% extra time** vs the original cycle budget.
- It does **not** require breaking a green gate already passed (e.g., do not re-touch a file already through STATIC).

**Procedure:**
1. Acknowledge the feedback in the conversation in one sentence.
2. Add an `Sn (ajout mid-cycle)` subtask to the PLAN file (do NOT renumber existing subtasks).
3. Log a `MID_CYCLE_AJOUT` entry in `action_journal.jsonl` with `trigger: user_observation` and the verbatim user phrase.
4. Execute as a normal OODA loop, but flag the verdict cell as `SUCCESS (ajout mid-cycle)` in the RETEX table.
5. If acceptance criteria fail -> queue the item in the RETEX `Improvements for c{N+1}+` block. Do NOT silently drop.

**RETEX section (mandatory when triggered):**

```
### Mid-cycle ajouts
- {user phrase}: triggered {Sn ajout} -> {verdict}
```

**Reference incident:** c38 S4 (2026-05-13). User said "186 c'est beaucoup" after S3 reported 191 truly-orphan distribution dominated by 186 `lia-declined` rows. Built `recover_lia_declined_aliases.py` (~190 LOC, 4-strategy lookup) within the cycle. Output surfaced 9 MEDIUM-tier candidates -> seeded c39 mig 164. Validates the pattern.

---

## Phase 4 : RECETTE (4-Step Blocking Validation)

When ALL subtasks are SUCCESS, enter the recette phase. Follow [recette-protocol.md](../_shared/references/recette-protocol.md).

### 4a. STATIC (BLOCKING)

Invoke via Skill tool (mandatory delegation):
- For each `*.rs` touched -> `Skill({skill: "rust-recette", args: "{file or crate}"})`
  (Blocs A-F / score /44, Bloc D = clippy + cargo-audit + cargo-deny + cargo-geiger,
  Bloc F = invariants I1-I6). The deep-scan helper `.claude/scripts/rust-recette-deep-scan.sh`
  runs Bloc D end-to-end. Tools installed via `scripts/install_rust_audit.sh` (a missing tool
  marks its bloc N/A, never invents a result).
- For each `*.py` touched -> `Skill({skill: "python-recette", args: "{file or package}"})`
  (Blocs A-F / score /44, Bloc D = ruff + pip-audit + mypy + bandit). Scorer:
  `cmd/python_recette` (`python -m python_recette --format json`). Tools in `.venv-pyaudit/`
  via `scripts/install_python_audit.sh` (missing tool -> bloc N/A).
- For each `*.tsx`/`*.ts` touched -> `/react-recette {file}` (48 checks, Bloc E = R17 Contract Gate).

**Recette-specific subjects (route by what the build touched, not just file extension):**
- Touched **corpus ground-truth** (`corpus/agents/`, `corpus/repos/`, `corpus/maf_agents/`,
  `corpus/sim/`, surface, an agent slug) -> the gate is the recette's OWN harness, not cargo:
  `make recette` (coverage-guard D1-D6 + validate + run + discovery + surface) and
  `./recette.sh test`. A coverage gap is a RED test, never patched by hand (R20). Discovery
  ground-truth stays invariant-based (detection/dedup/coverage/risk-order/determinism/policy),
  never opaque values. Negatives stay mono-axis (`test_each_negative_breaks_exactly_one_dimension`).
- Touched **docs** (any `.md` under `docs/` except `docs/plans`, `docs/tracking`,
  `docs/screenshots`, which the site excludes) -> the gate is `./recette.sh docs-build`
  (Docusaurus build of `docs-site/`). Output must show "[SUCCESS] Generated static files"
  + "docs-build OK". A doc that breaks the site build is a FAILURE (return to BUILD).
  Also enforced at cycle close by librarian-gate item 9. i18n: `docs/` is the fr
  source; mirror any fr change into `docs-site/i18n/en/docusaurus-plugin-content-docs/current/`.
  ARCHITECTURE.md mermaid is GENERATED (never hand-edit): edit
  `scripts/diagrams/architecture.py` (+ `architecture_i18n.py` for new labels),
  then `python3 scripts/gen_diagrams.py --write && --check` (must report
  "in sync: N diagrams x 2 locales").
- Touched **discoveryprobe** (separate Rust workspace) -> `cd discoveryprobe` before any cargo;
  the `discoveryprobe-ebpf` crate is EXCLUDED from the host workspace (`bpfel-unknown-none`
  target) -- if its toolchain/CAP_BPF is absent, mark that bloc N/A (R18), never a FAILURE.
  `cargo-geiger` audits the unsafe eBPF/loader surface; do not blanket-penalize necessary unsafe.

**Minimum scores**:
- `/rust-recette` >= 39/44 (or >= 35 with E+F N/A) AND zero CRITICAL in FAIL
- `/react-recette` >= 36/40
- Zero CRITICAL in FAIL (Rust: A1-A3, B1-B4, D1 clippy, D2 cargo-audit HIGH | React: A1-A3, B1-B2, C1-C2)
- Zero Bloc E (R17) in FAIL, zero Bloc F (invariant I1-I6) violated

If FAIL: return to Phase 3 BUILD. Create fix subtasks. Do NOT proceed to 4b.

### 4b. RUNTIME (BLOCKING)

Playwright smoke test on every impacted page:
```
mcp__playwright__browser_navigate -> impacted page URL
mcp__playwright__browser_snapshot -> verify zero "Component Error", "is not a function", "Cannot read properties of"
```

If FAIL: return to Phase 3 BUILD.

### 4b-bis. DESIGN / WCAG (BLOCKING -- for any modified `.tsx` rendering themed color)

Parity with `/audit-pdca` C.2bis (this gate was previously PDCA-only -- its absence in APEX
caused the 2026-05-24 EUVD rework loop: theme-token code passed every APEX gate yet failed
WCAG on 3 themes, surfacing cycles later). For any `.tsx` modified in the cycle that renders
chips, colored text, gradients, or tinted Paper:

1. Run the R25 static patterns (hardcoded white/black/hex, dark gradients, rgba overlays).
2. Invoke `/frontend-design` WCAG-audit on the modified components + transitive imports:
   render through the 6 active themes (Cyber, CyberMatrix, CyberRed, Classic, Heaven, Default),
   measure contrast (>=4.5:1 normal, >=3:1 large). Verdict FAILURE (any component unreadable
   in any theme) -> return to Phase 3 BUILD.
3. Enforce R31: chips/buttons use semantic `color="info|error|warning|success"` props (theme
   `MuiChip` override = contrast source of truth), NOT `sx={{ bgcolor: 'X.main', color:
   'X.contrastText' }}` (bypasses the override, hits unset contrastText -> WCAG fail).

A theme-token component is NOT done until its contrast is verified across the 6 themes.
Reference: `.claude/rules/theme-token-not-wcag.md` (R31), `.claude/rules/no-hardcoded-colors-in-tsx.md` (R25).

If FAIL: return to Phase 3 BUILD.

### 4c. CONTRACT (BLOCKING -- if API components)

R17 Contract Gate for each React component calling an API:
1. Capture real payload via curl -> save to `__fixtures__/{component}.fixture.json`
2. Write render-and-assert test with the fixture
3. Services consuming `{success, data}` MUST unwrap `.data`

If no API components modified: SKIP with justification in action_journal.

If FAIL: return to Phase 3 BUILD.

### 4d. REGRESSION

Delta scoring vs previous session:
- Compare current Rust static gate (clippy warnings count, test count) / react-recette scores with previous RETEX scores
- Run `cargo test` on all touched crates -- zero new failures vs pre-flight baseline
- Any regression = return to Phase 3 BUILD

### Cross-Cutting Checks (during 4a-4d)

- **Anti-patterns inspect_ia_agents**: R4 (no mock), R6 (structured logging), R7 (no unwrap), R10 (no emoji), R16 (Contract Gate)
- **Security OWASP**: SQL injection, XSS, command injection, path traversal
- **Adversarial review** (if `-x` or if >5 files): launch agent code-reviewer (sonnet)
- **Consistency check** (if `--swarms`): verify all components use same patterns (error handling, loading, empty states, HelpButton)
- **Doc gate** (if new endpoints): verify routes are in api-reference.md

If ISSUES FOUND: **FIX** (not just report) -> create fix subtasks -> return to BUILD loop.
Review must NEVER be read-only. Each warning = a fix to execute before COMPLETE.

### 4f. DEPLOY (USER-GATED -- only with `-d`/`--deploy` or explicit user GO)

Deploy is an **autonomy-boundary action** (see Autonomy Perimeter: "Deploy to
production = NO, always escalate"). APEX NEVER deploys on its own. This phase
runs ONLY when BOTH are true:
1. The cycle was invoked with `-d`/`--deploy`, OR the user gives an explicit
   GO in the conversation ("deploie", "fais", "push en prod", "active").
2. Phase 4a-4e all PASSED (a red gate forbids deploy).

Procedure (git-based, per `.claude/rules/deploy-workflow.md`):

1. **Confirm the deploy target with the user** if not already explicit. State
   what will change (backend binary, frontend bundle) and that it hits prod.
2. **Backend first** (has automatic rollback):
   ```
   ./deploy.sh backend
   ```
   Verify the deployed commit matches HEAD via `/api/diagnostic/build-info`
   (deploy.sh does this; a `BUILD MISMATCH` = FAIL -> stop, do not deploy frontend).
3. **Frontend second** (CAUTION -- `deploy.sh` frontend does `rm -rf assets`
   BEFORE build with NO rollback; a failed build = prod frontend 100% down,
   see `feedback_deploy_frontend_no_rollback`). Pre-condition: the frontend
   must have already passed `vite build` in Phase 1 pre-flight or an earlier
   gate. Then:
   ```
   ./deploy.sh frontend
   ```
   If it fails: recover by rsyncing a known-good `dev/.../build/` to
   `source/.../build/` and reload nginx -- do NOT leave prod down.
4. **Post-deploy live smoke (R26, BLOCKING for the "deployed" claim)**:
   - `./deploy.sh status` -> all services active.
   - Playwright navigate the deployed feature page on the prod URL
     (https://inspect_ia_agents.example/...), assert zero console error + the expected
     DOM node. For themed UI, run the 6-theme WCAG smoke here against prod.
   - Only after this passes may the cycle report "deployed AND verified".
     Otherwise use the R26 escape phrase ("deploye, non verifie" + reason).
5. **Branch discipline**: if deploying a feature branch, either merge to
   master first (preferred for `pull-all`) or document that prod was deployed
   from the branch build (rsync path) and a master merge is still pending.

If DEPLOY fails or live smoke fails: the cycle does NOT report success.
Log the failure in action_journal + decision_log and either rollback or
escalate.

---

## Phase 5 : COMPLETE (Learning + Capitalization)

**OODA: the phase absent from Boyd -- learning.**

### Librarian Gate (BLOCKING)

Follow [librarian-gate.md](../_shared/references/librarian-gate.md):

```
[ ] 1. PLAN up to date : docs/tracking/PLAN_APEX_{NAME}_{DATE}.md (Status: TERMINE)
[ ] 2. RETEX written   : docs/tracking/retex/RETEX_APEX_{DATE}.md
[ ] 3. RETEX DISPLAYED : RETEX content DISPLAYED in the conversation (not just written to file)
[ ] 4. DURABLE DOC (SI PRODUIT) : a lasting doc/runbook change goes in committed `docs/` (NOT docs/tracking/). Rebuild a docs site only if this repo has one.
[ ] 5. UI HELP (BLOQUANT, SI FRONTEND) : INSERT ui_help_content + verify SELECT for EACH new *Tab/*Panel/*Dashboard/*Editor component. FAIL = cycle CANNOT close.
[ ] 6. Clean commit    : ONLY committed deliverables (source, corpus, the skill). NEVER `git add` anything under docs/tracking/ (R25). Never `git add -A`.
[ ] 7. Push            : max 5 unpushed commits
```

### RETEX (MANDATORY -- display in conversation)

Follow [retex-protocol.md](../_shared/references/retex-protocol.md):

```
## RETEX APEX -- {title}
Date : {YYYY-MM-DD}
Agentic score : {N}/50

| Criterion | Score | Comment |
|-----------|-------|---------|
| C1 Decomposition | /10 | 3-7 subtasks, complexity scored, dependencies explicit |
| C2 Planning (THINK) | /10 | Research done, 2+ alternatives evaluated, adversarial critique integrated |
| C3 Replanning | /10 | REPLAN triggered on FAILURE, 2+ alternatives each time |
| C4 Tooling | /10 | Model haiku/sonnet selected per task, skills invoked, pipelines followed |
| C5 Traceability | /10 | action_journal + decision_log + swarm_memory + RETEX displayed |

Subtasks: {N} total, {S} SUCCESS, {P} PARTIAL, {F} FAILURE, {R} REPLAN
OODA loops: {N} total cycles
THINK phase: {N} alternatives evaluated, {N} rejected, critique findings integrated: {yes/no}
What worked: ...
What failed: ...
Improvements: ...
```

### C2 Scoring Guide (v6.0 update)

C2 now evaluates the THINK phase quality:
- 9-10/10: Research thorough, 3+ alternatives with detailed pros/cons, adversarial critique run AND feedback integrated, plan adjusted based on critique
- 7-8/10: 2 alternatives evaluated, critique run, minor feedback integrated
- 5-6/10: 2 alternatives listed but superficial, critique skipped or ignored
- 3-4/10: 1 alternative only, no critique
- 0-2/10: No THINK phase, jumped straight to BUILD

### Session Manifeste

At session end, write manifeste.jsonl listing all files produced/modified with their final status. See [action-journal-spec.md](references/action-journal-spec.md).

### Evolutions (Bloc 9 CLAUDE.md)

- Quick win (5 min, high impact)
- Notable improvement (30min-2h)
- Significant refactor (half-day+)

Compare with state of the art (link/benchmark). Propose automation if repetitive.

---

## Model Selection Strategy (MANDATORY)

| Task | Model | Parameter |
|------|-------|-----------|
| Exploration (Glob/Grep/Read) | **haiku** | `model: "haiku"` |
| Compliance (grep patterns) | **haiku** | `model: "haiku"` |
| Dead code (grep + count) | **haiku** | `model: "haiku"` |
| Documentation (file presence) | **haiku** | `model: "haiku"` |
| Code review OWASP | **sonnet** | `model: "sonnet"` |
| Architecture review | **sonnet** | `model: "sonnet"` |
| Code generation | **sonnet** | `model: "sonnet"` |
| Adversarial plan critique | **sonnet** | `model: "sonnet"` |
| Orchestration APEX | **opus** | inherited from parent |

**NEVER a haiku-eligible agent on opus.**

---

## Memory 3 Levels

Detailed in [agentic-core.md](../_shared/references/agentic-core.md). Summary:

### Level 1: Working memory (session)

- `action_journal.jsonl`: each action + verdict + gate results
- `FILE_TRACKER.json`: modified files + status (recovery on resume)
- `swarm_memory.json`: inter-agent shared state (if `--swarms`)
- Local variables: subtasks, verdicts, REPLAN counters

### Level 2: Long-term memory (inter-session)

- `docs/tracking/retex/`: previous session RETEX
- `docs/tracking/decision_log.jsonl`: non-trivial decisions
- `.claude/memory/`: user feedback, preferences

### Level 3: Action Journal (append-only, audit trail)

Each action logged with context, result, and resulting decision. Non-modifiable. Serves as audit trail to understand why each decision was made.

**At APEX startup**: load the most recent RETEX from the same domain. Apply identified improvements. Do NOT repeat already-documented mistakes.

---

## Autonomy Perimeter

| Action | Autonomous | Escalation |
|--------|-----------|------------|
| Read/explore code | YES | - |
| Edit file in scope | YES | - |
| Create new file | YES | - |
| Build + test | YES | - |
| Commit (conventional) | YES | - |
| Push | YES (max 5 unpushed) | - |
| Modify auth/security | NO | Always escalate |
| DDL (ALTER/CREATE TABLE) | NO | Always escalate |
| Delete file/code | NO | Always escalate |
| >10 files in 1 batch | NO | Ask confirmation |
| Deploy to production | NO | Always escalate |

---

## Flow Diagram

```
Phase 0: INIT
    |-- parse task, generate session id
    |-- create PLAN_APEX_*.md IMMEDIATELY
    |-- pre-flight (build Rust + React)
    |-- load FILE_TRACKER if --resume
    v
Phase 1: OBSERVE
    |-- cartography (files, deps, git status)
    |-- load previous RETEX (same domain)
    |-- health scan (display results)
    v
Phase 2: THINK
    |-- 2a: research codebase (+ web if --research)
    |-- 2b: 2+ alternatives evaluated
    |-- 2c: structured plan (3-7 subtasks)
    |-- 2d: adversarial critique (sonnet agent)
    |-- create swarm_memory.json if --swarms
    v
Phase 3: BUILD (loop per subtask)
    +---> ACT (execute, Rust/Python/React pipeline per file)
    |       |
    |       v
    |     OBSERVE (build gate, vet, test, runtime crash)
    |       |
    |       v
    |     EVALUATE
    |       |-- SUCCESS -> next subtask
    |       |-- PARTIAL -> adjust + continue
    |       +-- FAILURE -> REPLAN (2+ alternatives)
    |                        |-- 3 fails -> ESCALADE
    |                        +-- else -> back to ACT
    |
    v (all subtasks SUCCESS)
Phase 4: RECETTE
    |-- 4a: STATIC (/rust-recette [clippy+audit+deny+geiger] + /react-recette) -- BLOCKING
    |-- 4b: RUNTIME (Playwright smoke test) -- BLOCKING
    |-- 4c: CONTRACT (R17 fixtures) -- BLOCKING if API components
    |-- 4d: REGRESSION (delta scoring)
    |-- FAIL on any -> return to Phase 3 BUILD
    v
Phase 5: COMPLETE
    |-- Librarian Gate (blocking checklist)
    |-- RETEX written + DISPLAYED in conversation
    |-- Manifeste JSONL
    |-- Evolutions proposed
    +-- DONE
```

**NEVER: choice menu, "shall we continue?", table without action, "do you want me to commit?"**
**ALWAYS: loop, evaluate, decide, act. Escalate only when necessary.**

---

## References (APEX-specific)

| File | Content |
|------|---------|
| [references/action-journal-spec.md](references/action-journal-spec.md) | Action journal, staging protocol, manifeste JSONL, FILE_TRACKER v2 |
| [references/agent-delegation-protocol.md](references/agent-delegation-protocol.md) | APEX-specific agent roles, delegation format, autonomy |
| [references/quality-hooks.md](references/quality-hooks.md) | QH-A1..A5, OODA security layer, context management |

---

## D.5 No-Birth-Over-Ceiling (R29 anti-anssi-1864)

A new file created by APEX MUST NOT be born above the LOC ceiling
(.rs 800 / .ts 500 / .tsx 400) -- bare or compliant `@allow-long-file`
marker does NOT exempt creation. Pre-commit hook blocks files in
`git diff --cached --name-only --diff-filter=A` with LOC > ceiling
regardless of marker. If a generated file would exceed ceiling, BUILD
phase MUST chain `/refactor-long-file` before commit (emit the split
modules, not a single over-ceiling file). Incident reference:
a generated handler born 1554 LOC, grew to 1864 LOC -- exactly
the silent bypass pattern R29 was designed to prevent. Editing a
legacy over-ceiling file is unaffected (delta-scoped to creation).
