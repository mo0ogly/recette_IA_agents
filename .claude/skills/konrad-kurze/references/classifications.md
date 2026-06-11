# Konrad-Kurze -- Failure Classifications

Five canonical failure classes. A single Konrad run can produce more than one classification, but the dominant class (highest confidence) drives the directive.

## Table of contents

1. CONVENTION_CONFLICT
2. GHOST_REDUNDANCY
3. META_DATA_AMNESIA
4. PHYSICAL_VISUAL_MISMATCH
5. LEMANRUSS_TAINT (guarded)
6. Composite signatures
7. False-positive guards

---

## 1. CONVENTION_CONFLICT

The cycle keeps failing because code touched by it violates an LIA-SEC rule (R1..R26). The fix is mechanical -- the agent has been re-introducing or not removing the violation.

### Detection probes

- `grep -rE "fmt.Println|console.log|API_BASE_URL =|<Grid item " {touched_files}` -> non-zero hit
- `C_SCORECARD.json` shows `code_hygiene` or `security` domain unchanged across 2+ cycles
- `decision_log.jsonl` has 2+ entries with `action="REPLAN"` and `reasoning` mentioning the same rule id
- `RETEX_*.md` cycle N-1 marked the rule as "to fix" but cycle N still fails on it

### Confidence multipliers

- +0.2 if the rule id appears verbatim in C_GAP_REPORT.md
- +0.1 if the same file is re-edited across cycles
- -0.2 if the code path is in `_archive/` (dead code)

### Example signature

```
classification: CONVENTION_CONFLICT
evidence_refs:
  - sigma-react-frontend/src/components/foo/Bar.tsx:42 ("fontFamily: 'monospace'")
  - .claude/rules/anti-patterns.md (R-frontend fonts)
  - pdca/foo/cycle_002/C_GAP_REPORT.md:18 ("HYG-03 unchanged")
```

---

## 2. GHOST_REDUNDANCY

The same fix is being applied across 2+ cycles. Either the prior fix was reverted, or the agent forgot it was already done.

### Detection probes

- `git log --since "{N cycles ago}" --oneline -- {file}` shows 2+ commits with similar messages
- `decision_log.jsonl` has 2+ entries with same `action` and similar `outcome` on same file
- `pdca/{module}/cycle_*/agent_outputs/*.json` show overlapping subtask names across cycles
- `C_SCORECARD.json` shows score increase then decrease then increase on same domain

### Confidence multipliers

- +0.2 if `git diff cycle_N-1..cycle_N` is essentially the same as `git diff cycle_N-2..cycle_N-1`
- +0.1 if both prior commits have the same scope keyword in subject

### Example signature

```
classification: GHOST_REDUNDANCY
evidence_refs:
  - git log: cycle_002 commit abc123, cycle_003 commit def456 (same file, same change)
  - decision_log:2026-04-20T14:00:00Z action=APPLY_FIX outcome=COMPLETE
  - decision_log:2026-04-22T16:00:00Z action=APPLY_FIX outcome=COMPLETE (same file)
```

---

## 3. META_DATA_AMNESIA

A required side-artefact is missing -- and the cycle does not realize it is the missing piece. Common cases: missing `__fixtures__/*.fixture.json` (R17), missing `ui_help_content` row (R8), missing tracking entry (`PLAN_*.md`) or `.doc-meta.json` (R15).

### Detection probes

- `C_GAP_REPORT.md` mentions "fixture" or "UI help" or "doc metadata" without resolution
- `find sigma-react-frontend/src/components/{module} -name "__fixtures__" -type d` returns empty for a module that calls APIs
- `find _alire/01_DOCUMENTATION/{type} -name "{module}*"` returns 0 results for new module
- PostgreSQL `SELECT count(*) FROM ui_help_content WHERE component='...'` returns 0 for screens that should have help

### Confidence multipliers

- +0.3 if the rule (R8 / R15 / R17) is explicitly cited in retex but no follow-up
- +0.1 if the cycle FINALIZE was reached without satisfying Librarian Gate

### Example signature

```
classification: META_DATA_AMNESIA
evidence_refs:
  - sigma-react-frontend/src/components/foo/__fixtures__/ (DOES NOT EXIST)
  - .claude/rules/frontend-contract-gate.md (R17)
  - pdca/foo/cycle_003/C_GAP_REPORT.md:34 ("R17 fixture missing")
```

---

## 4. PHYSICAL_VISUAL_MISMATCH

The code compiles, types check, fixtures exist, but the rendered UI is broken -- contrast, theme, R23 chart labels, or runtime crash on real payload. The cycle's static checks are blind to this.

### Detection probes

- `RETEX_*.md` mentions "screenshot", "theme", "WCAG", "unreadable", "labels overlap"
- The UnifiedResultsTreeView 2026-04-24 incident pattern: hex gradient + hardcoded `color: 'white'` + no `useTheme`
- Playwright smoke test in cycle was missing the user-flow assertion (R26 violation)
- C.2bis design audit verdict was FAIL or skipped

### Confidence multipliers

- +0.2 if `_alire/02_LOGS/Journals/design_audit/*.md` for the cycle has WCAG fail
- +0.2 if user reported the issue verbatim ("tout noir avec ecriture noire" pattern)
- +0.1 if hardcoded gradient detected by R25 audit command

### Example signature

```
classification: PHYSICAL_VISUAL_MISMATCH
evidence_refs:
  - sigma-react-frontend/src/components/foo/Bar.tsx:88 (linear-gradient(135deg, #263238 ...))
  - .claude/rules/no-hardcoded-colors-in-tsx.md (R25)
  - _alire/02_LOGS/Journals/design_audit/2026-04-24_cycle-3_design.md (WCAG fail Heaven theme)
```

---

## 5. LEMANRUSS_TAINT (GUARDED)

The PDCA loop is using its own assumption as input. Symptom: cycle N "fixes" something that was never broken, because cycle N-1 mis-classified the symptom and cycle N-2 propagated the wrong frame.

### MANDATORY guards (must all be true)

1. >= 2 consecutive cycles failed with the same diagnosis text
2. The diagnosis contradicts `C_USAGE_TRIAGE.md` or the most recent `PLAN_*.md`
3. NO agent-level error (subagent exception, tool failure) is detected on the failing cycles
4. QK-04 LemanRuss Challenge passed (a 2nd evidence source, independent of PDCA's own logs, exists)

If any guard fails, downgrade to one of the other 4 classifications or drop.

### Detection probes

- `decision_log.jsonl`: 2+ entries with same `reasoning` snippet across cycles
- `C_GAP_REPORT.md` cycle N references "still failing on X" but `git log -- X` shows the area was modified
- An external signal (user feedback, hook output, Playwright recording) contradicts the cycle's narrative

### Confidence ceiling

LEMANRUSS_TAINT MAX confidence = 0.7. Always requires user approval if the directive is MODIFY or REMOVE.

### Example signature

```
classification: LEMANRUSS_TAINT
evidence_refs:
  - decision_log: cycle_002 + cycle_003 same reasoning "test must mock DB"
  - .claude/rules/feedback_never_alter_db_credentials.md (contradicts the assumption)
  - swarm_memory.json:cycle_003 known_issues missing the contradiction
```

---

## 6. Composite signatures

A single Konrad run may produce multiple classifications. Rules:

- If 2 classifications have confidence within 0.1 of each other: emit BOTH in the directive, dominant first.
- Never combine LEMANRUSS_TAINT with itself across runs as a "stronger evidence" -- it is always a per-run claim.
- If CONVENTION_CONFLICT and META_DATA_AMNESIA both fire on the same artefact: prefer META_DATA_AMNESIA (root) over CONVENTION_CONFLICT (symptom).

## 7. False-positive guards

Reject a classification (do not emit) when:

- The probe matches files in `_archive/`, `node_modules/`, `vendor/`, `dist/`
- The probe matches a comment in `.md` documentation describing the anti-pattern itself
- The cycle that "failed" was explicitly closed as PARTIAL with a documented dette in retex (the agent KNEW it would not fix this in cycle N)
- All evidence_refs point to files older than the trigger event by 90+ days (likely stale evidence)
