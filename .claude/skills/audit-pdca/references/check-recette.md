# Contrôles de recette locaux

Les chemins textuels restent relatifs au dépôt ou à la skill d’origine.
Le scoring commun méthode 2 remplace les anciennes moyennes pour les nouveaux rapports.

## Phase C -- CHECK / RECETTE (4 sequential blocking steps)

Follow `recette-protocol.md` for the full 4-step protocol. Summary below.

### C.0 : Dead Code Filter (MANDATORY before scoring)

```bash
cargo build 2>&1 | grep -E "never used|dead_code"   # compiler dead-code warnings
grep -rn "fn symbol_name" src/ --include='*.rs'      # find definition
grep -rn "symbol_name" src/ --include='*.rs' | grep -v "fn symbol_name" | wc -l   # count callers
```

Classify: ACTIF / PROTOTYPE / DEAD.
Only ACTIF code participates in scoring. DEAD code excluded, proposed for .disabled.

### C.1 : STATIC -- /rust-recette + /react-recette (BLOCKING)

**This is NOT a passive reference. It is a mandatory delegation via Skill tool.**

For each file modified in the cycle:

**If `*.py` (backend)**: invoke `Skill({skill: "python-recette", args: "{file or package}"})`
  - Blocs A-F / score /44 (D = ruff + pip-audit + mypy + bandit, F = invariants I1-I6)
  - **BLOC D SCORE = security domain score** (see build-pipeline-python.md, /20)
  - Scorer: `cmd/python_recette`. Reference: `.claude/commands/python-recette.md`

**If `*.rs` (backend)**: invoke `Skill({skill: "rust-recette", args: "{file or crate}"})`
  - Blocs A-F / score /44 (A conventions, B OWASP Rust, C arch/perf, D static = clippy+cargo-audit+cargo-deny+cargo-geiger, E R17 Contract Gate, F invariants I1-I6)
  - **BLOC D SCORE = security domain score in SCORING_CONFIG (converted /20, see build-pipeline-rust.md)**
  - clippy + cargo-audit + cargo-deny + cargo-geiger: real SAST / supply-chain tools, superior to any manual grep
  - Helper: `.claude/scripts/rust-recette-deep-scan.sh` runs Bloc D end-to-end. Tools installed via `scripts/install_rust_audit.sh`. A missing tool marks its bloc N/A (R18, never invent a result).
  - Reference: `.claude/commands/rust-recette.md`

**If `*.tsx`/`*.ts` (frontend)**: invoke `Skill({skill: "react-recette", args: "{file or directory}"})`
  - 6 blocs / 48 checks (A conventions, B OWASP, C Vercel perf, D react-doctor, E R17 Contract Gate, F legacy health)
  - **BLOC B SCORE = security domain score in SCORING_CONFIG (converted /20)**
  - Reference: `.claude/commands/react-recette.md`

**Sub-skill SCORE CONTRACT (BLOCKING -- every delegated recette returns a number).**
A delegated recette is not a pass/fail vibe; it MUST return a numeric score that maps into
the scorecard. The cycle CANNOT score a domain whose recette returned no number -- that
domain is `A_VERIFIER` (re-run the recette), never scored at feeling (anti-confabulation).

| Sub-skill | Returns | Maps into domain |
|-----------|---------|------------------|
| `/rust-recette` | /44 total + Bloc D /N | testing+hygiene+arch from total; **Bloc D -> security /20** |
| `/python-recette` | /44 total + Bloc D /N | same; **Bloc D -> security /20** |
| `/react-recette` | /40 (6 blocs/48 checks) + Bloc B /N | hygiene+arch+completeness; **Bloc B -> security (B/10*20)** |

The returned number is recorded verbatim in `C_SCORECARD.json.domains[].src` (which recette,
which bloc, what value). A domain score that does not trace to a recette number or a config
check `evidence_grep` count is INVALID (anti-confabulation, see scoring-config.md penalty model).

**Security domain score integration:**
```
security domain score = Rust/Python security score /20 (build-pipeline, Bloc D)
                        OR
                        react-recette BLOC B score / 10 * 20
```

**Cycle FAILURE and return to Phase D if:**
- `/rust-recette` < 39/44 (or < 35 with E+F N/A)
- OR `/react-recette` < 36/40
- OR a single Bloc E (R17) check FAIL for a component/handler calling an API
- OR a single Bloc F (invariant I1-I6) violated
- OR a CRITICAL check FAIL:
  - React: A1 (Grid v7), A2 (URL hardcode), A3 (Logger), B1 (XSS), B2 (Secrets), C1 (barrel imports), C2 (Promise.all)
  - Rust: A1 (tracing), A2 (no panic fallible), A3 (secrets), B1 (SQLi), B2 (CmdInj), B3 (Secrets), B4 (Auth/identity), D1 (clippy -D warnings), D2 (cargo-audit HIGH/CRITICAL)

No exception, no "we will do it in the next wave".

**Multi-track scope filtering (A3)**: in a shared working tree mutated
by concurrent sessions, a global `tsc --noEmit` / `cargo build` will
surface PRE-EXISTING errors in other-track files (e.g. another crate,
another module). These do NOT FAIL the cycle. Filter the gate to
the cycle scope:
```bash
npx tsc --noEmit 2>&1 | grep -E "{scope path regex}" && echo "SCOPE ERRORS" || echo "SCOPE CLEAN"
```
Out-of-scope errors are flagged (decision_log + RETEX) under R28
flag-not-sweep, NOT fixed, NOT swept, NOT a cycle FAILURE. Only errors
in files this cycle touched count.

**Context-budget equivalence (A4)**: the `/rust-recette` /
`/react-recette` delegation is the default and is MANDATORY when any
check is HIGH/CRITICAL or the verdict is uncertain. When the context
budget is constrained (long swarm session, many agent reports already
integrated) an inline pattern-scan of the same checks (grep for A1
Grid-item, A2 hardcoded-URL, A3 console, B1 dangerouslySetInnerHTML,
B2 secrets, C1 barrel-imports, F2 raw-fetch, R25 colors, plus `tsc`
scope-clean + nested-component + index-key) is an ACCEPTED equivalent
for the BLOCKING gate, provided: (a) zero CRITICAL pattern matched,
(b) the scan is logged in decision_log, (c) any single HIGH/CRITICAL
hit escalates to the full Skill delegation. This reconciles the
protocol with real token cost; it is NOT a license to skip recette --
the checks are still all run, just inline.

### C.2 : RUNTIME -- Playwright smoke test (BLOCKING)

For each page impacted by modifications:
1. Navigate with Playwright to the page
2. Take snapshot, check for: "Component Error", "is not a function", "Cannot read properties", blank page
3. Verify at least one expected DOM element renders correctly

FAIL = return to Phase D with concrete error to fix.

### C.2bis : DESIGN AUDIT -- R25 hardcoded colors (BLOCKING for any `.tsx` modification)

**Scope**: every `.tsx` file modified in the cycle **AND all components transitively imported**
(depth ≥ 2: `components/reports/X.tsx` → `components/system/Y.tsx` → `components/common/Z.tsx`).
To resolve transitive scope: `grep -r "import.*from" {modified_file} --include="*.tsx"` recursively.
Reason: incident 2026-04-24 — `UnifiedResultsTreeView.tsx` lived in `components/system/` and was
never in scope of cycles targeting `components/reports/` only (R25, `.claude/rules/no-hardcoded-colors-in-tsx.md`).

Each pattern that matches triggers a **FAIL** -> return to Phase D.

**A. Button/IconButton/Chip with hardcoded `color: 'white'` or `'black'`**
```bash
# Find color: 'white'/'black' without adjacent contrastText (theme-unaware)
for f in $(grep -rlE "color: '(white|black)'" --include="*.tsx" inspect_ia_agents-console/src/ | grep -v "/themes/\|/constants/\|_archive/"); do
  if ! grep -q "contrastText\|theme.palette.getContrastText" "$f"; then
    echo "R25 FAIL: $f -- color white/black without theme awareness"
  fi
done
```

**B. `borderColor: 'white'` on bordered elements**
```bash
grep -rn "borderColor: 'white'\|borderColor: 'black'" --include="*.tsx" inspect_ia_agents-console/src/ | grep -v "/themes/\|/constants/\|_archive/"
```

**C. Tremor `badgeColor` with invalid values**

Valid Tremor v4 values: `"blue" | "gray" | "green" | "orange" | "red"`.
Any other named color (`emerald`, `cyan`, `yellow`, `amber`, `violet`, `rose`, etc.) causes TS2322.

```bash
grep -rn 'badgeColor="' --include="*.tsx" inspect_ia_agents-console/src/ | \
  grep -vE 'badgeColor="(blue|gray|green|orange|red)"'
# Any match = invalid Tremor color -> replace with closest valid equivalent:
# emerald -> green | cyan -> blue | yellow/amber -> orange | rose/pink -> red
```

**D. Hardcoded `bgcolor: '#RRGGBB'` on containers**
```bash
# ERE with {3,8} quantifier to match real hex strings (3 to 8 hex chars)
grep -rnE "bgcolor: '#[0-9a-fA-F]{3,8}'" --include="*.tsx" inspect_ia_agents-console/src/ | \
  grep -v "/themes/\|/constants/\|_archive/"
```

**E. Dark hex gradients (existing R25 check, reminder)**
```bash
grep -rn "linear-gradient" --include="*.tsx" inspect_ia_agents-console/src/ | \
  grep "#[0-4]" | grep -v "/themes/\|/constants/\|_archive/"
```

**F. Dark overlay `rgba(0,0,0,...)` as component background** (R25 -- 20 occurrences at rule creation)
```bash
grep -rn "bgcolor: 'rgba(0,0,0" --include="*.tsx" inspect_ia_agents-console/src/ | \
  grep -v "position: 'fixed'" | grep -v "/themes/"
# Exception: position:fixed backdrops (Dialog/Modal dimming) are allowed
```

**G. Dialog without maxHeight or overflow (R21)**
```bash
grep -rn "<Dialog" --include="*.tsx" inspect_ia_agents-console/src/ | \
  grep -v "maxHeight\|/themes/\|_archive/" | grep -v "//.*<Dialog"
# Any Dialog missing maxHeight: '90vh' on PaperProps = R21 violation
```

**H. Chart/visualization with 4+ inline labels without leader lines (R23)**
```bash
grep -rn "angularExternalLabels\|deOverlapLabels" --include="*.tsx" inspect_ia_agents-console/src/
# Any *Radar.tsx, *Chart.tsx, *Graph.tsx NOT using these helpers for 4+ labeled marks = R23 violation
grep -l "Radar\|Bubble\|Scatter" inspect_ia_agents-console/src/components/**/*.tsx 2>/dev/null | \
  xargs grep -L "angularExternalLabels\|deOverlapLabels" 2>/dev/null
```

**Fix pattern** for each finding:
```tsx
// FORBIDDEN
color: 'white'
bgcolor: '#1a237e'
borderColor: 'white'
badgeColor="emerald"
bgcolor: 'rgba(0,0,0,0.3)'   // on non-fixed container

// REQUIRED
color: theme.palette.primary.contrastText
bgcolor: theme.palette.primary.dark
borderColor: theme.palette.divider
badgeColor="green"
bgcolor: alpha(theme.palette.background.default, 0.6)
```

**WCAG AA contrast verification** (for cycles modifying 3+ .tsx files or finding any pattern above):
```
Skill({skill: "frontend-design", args: "WCAG-audit: verify contrast ratio on all modified .tsx files
and their transitive imports through the 6 active themes (Cyber, CyberMatrix, CyberRed, Classic,
Heaven, Default). Threshold: >=4.5:1 normal text, >=3:1 large text (WCAG AA).
Report: PASS/FAIL per component per theme. Output to docs/tracking/pdca/{scope}/cycle_{N}/design_audit.md"})
```
Verdict `FAILURE` (>=1 component unreadable in any theme) -> REPLAN obligatoire. Reference: R25.

Reference: `.claude/rules/no-hardcoded-colors-in-tsx.md` (R25), R21, R23
Incident: 2026-04-25 -- CyberTheme primary.main = '#00FFFF' (cyan) -> MUI contrastText = black;
buttons with `color: 'white'` were invisible. PDCA cycles missed this until user reported it.

FAIL = any pattern A/B/C/D/E/F/G/H found -> fix all occurrences, return to Phase D, re-run C.2bis.

### C.3 : CONTRACT -- R17 (BLOCKING if API components)

**Triggers** — component must pass this gate if ALL true:
- File matches `*Tab.tsx`, `*Panel.tsx`, `*Status.tsx`, `*Dashboard.tsx`, `*Manager.tsx`, `*Editor.tsx`
- AND contains a `fetch` call or a direct service function call returning API data

For each qualifying component:
0. If no API Handoff document exists for this endpoint: run `/api-handoff {feature} --r17` to capture the contract before writing tests
1. Capture real payload with curl -> `__fixtures__/{component}.fixture.json`
2. Write render-and-assert test with captured fixture (zero runtime errors, expected DOM element present)
3. Verify service-layer unwraps `.data` from `{success, data}` envelope (never `return resp.json()` direct)
4. Smoke test via Playwright post-deploy: navigate to component, assert zero console errors + at least one expected DOM element visible

See `.claude/rules/frontend-contract-gate.md` for full R17 protocol.

Components that do not call APIs: skip this step.

### C.4 : REGRESSION -- delta scoring (BLOCKING)

If cycle > 1:
1. Load `C_SCORECARD.json` from cycle N-1
2. Calculate delta per domain
3. **Zero regression tolerance**: any domain dropping > 5 points = FAIL
4. If regression detected: identify cause, return to Phase D with targeted fix plan

### C.5 : Scorecard consolidation

For each domain, derive penalties from frozen checks and real evidence with the shared method-2 evaluator; compare only compatible final outputs.

**Global score** = shared method-2 weighted score; provisional evidence never permits delivery.

**Cycle classification:**

| Score | Verdict | Action |
|-------|---------|--------|
| >= target | **COMPLETE** | -> Phase F (FINALIZE) |
| 85-target | **PARTIAL** | -> Phase D (targeted fixes) |
| < 85 | **FAILURE** | -> Phase D (full remediation) |

Output: `C_SCORECARD.json` + `C_GAP_REPORT.md`

### C.6 : Conditional replanification

If score < 50 or 3+ domains in regression: generate an adjusted plan with 2+ alternatives.
Log in `decision_log.jsonl`.

---
