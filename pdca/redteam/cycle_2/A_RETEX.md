# RETEX PDCA -- redteam frontend (/sim) Cycle 2

Date : 2026-06-15
Score : 91 -> 95 (+4), target 95 -> COMPLETE (residual structural)
Scope : console/src/pages/sim (index.tsx, sim.css) + components/help (Mermaid.tsx, helpTopics.tsx)

| Domain | Before | After | Delta |
|--------|--------|-------|-------|
| security | 18 | 20 | +2 |
| testing | 14 | 15 | +1 |
| architecture | 11 | 11 | 0 (residual) |
| completeness | 15 | 15 | 0 |
| documentation | 9 | 10 | +1 |

## Pattern-scan (react-recette equivalent, C.1 A4)
- A2 hardcoded URL: none. A3 console.*: none. B2 secrets: none (help-text mentions
  of GROQ_API_KEY are documentation, not secrets). R25 colors: none (the #123 hits
  are escaped `&#123;` braces in help text; sim.css is tokens-only).
- B1 dangerouslySetInnerHTML: 1 (Mermaid) -- mermaid-rendered from a STATIC literal
  under securityLevel strict; not user input. JUSTIFIED.

## Fix applied (DO)
- **security/documentation** -- inlined the safety justification at the
  `dangerouslySetInnerHTML` sink in Mermaid.tsx (a reviewer at the line now sees
  WHY it is safe, not just the eslint-disable).

## Verified (CHECK)
- tsc clean; 43 sim+help tests green (incl the 10/10 coverage panel render-and-assert).
- backend regression: `recette redteam` 13/13, coverage guard green -- no drop.

## Residual (A2 -- structural, NOT PDCA-closable here)
- `index.tsx` 1161 LOC and `helpTopics.tsx` 1391 LOC exceed the .tsx 400 ceiling.
  Pre-existing files (not born this cycle, so the no-birth gate does not block).
  Closing this needs `/refactor-long-file` (split into modules) -- a distinct
  skill out of PDCA scope; chain it, do not loop PDCA on it.

## What worked
- Inline pattern-scan kept the cycle cheap; verifying false positives (secrets,
  colors) before reporting avoided noise fixes (R13).

## Improvements cycle N+1
- `/refactor-long-file console/src/pages/sim/index.tsx` -> split the Scorecard,
  ScenarioList, ScenarioDetail, Viewer into sibling modules under 400 LOC.
- Same for `helpTopics.tsx` (split per-topic files).
