---
name: refactor-long-file
description: Split a React or Go file that exceeds the project size ceiling (400 LOC for .tsx, 500 LOC for .ts, 800 LOC for .go) into an orchestrator + presentation/helper modules, each under the ceiling. Produces a dependency graph, candidate module boundaries, per-module R17 fixture + render-and-assert test, and a migration commit. Invoke when a file trips the pre-commit file-size hook, when a file carries // @allow-long-file as technical debt, or when a TDZ/hook-ordering bug surfaces in a monolithic component (the split makes hook order explicit and closes the bug class). Triggers on "/refactor-long-file", "split this file", "trop long", "refactor monolithique", "@allow-long-file cleanup", or automatically after a file crosses its ceiling in /react-recette or /go-recette. References the successful Nis2ByArticles precedent (2026-04-24, 1145 -> 334 LOC + 9 modules, 4/4 tests green).
---

# /refactor-long-file -- split a monolithic .tsx / .ts / .go into orchestrator + modules

## Why this skill exists

Files above the project ceiling (400 LOC `.tsx`, 500 LOC `.ts`, 800 LOC
`.go`) accumulate multiple classes of bugs:

- **TDZ / hook-ordering bugs** : a derived value references a `useState`
  declared below it. Minified bundles crash as "Cannot access 'C' before
  initialization" (Nis2ByArticles incident 2026-04-24).
- **Implicit coupling** : presentation code knows internal state of the
  orchestrator, making each fix risky.
- **No R17 gate** : a 1000-LOC component is too big to mock / fixture
  / render-test in one file.
- **Pre-commit hook noise** : `// @allow-long-file` markers silently
  pile up and become permanent.

The fix is a standard split: one **orchestrator** (owns data fetch,
state, top-level layout) + N **presentation / helper modules** (each a
single responsibility, each under the ceiling, each with its own R17
fixture if it touches an API).

## When to invoke

- Any file marked `// @allow-long-file` that is not a pure vendor file
- Any file that trips `check_file_size.sh` pre-commit hook
- A file containing a TDZ bug reported in production (refactor closes
  the class, not just the symptom)
- `/react-recette` or `/go-recette` reports "file too long" finding
- User asks "refactor X" / "split X" / "X est trop long"

DO NOT invoke this skill:
- On vendor / generated code (leave `// @allow-long-file` with a note)
- On a file you haven't read end-to-end (you will miss boundaries)
- On a file that is about to be deleted (don't waste effort)

## Ceilings (authoritative)

| Extension | Ceiling | Rationale |
|---|---|---|
| `.tsx` | 400 LOC | React component complexity budget (Nis2 precedent) |
| `.ts`  | 500 LOC | Logic-heavy modules tolerable but harder to test at 500+ |
| `.go`  | 800 LOC | Go handlers tolerate more volume but 800+ hurts godoc |
| `.py`  | 500 LOC | Scripts readable below 500 |

Override only with a commented `// @allow-long-file -- justification` line
on line 1 of the file.

## Workflow -- 6 phases

### Phase 1 : OBSERVE (read the whole file)

1. Read the file end-to-end. No skipping.
2. `wc -l` and `grep -c '^(function\|const.*=>\|class\|export)'` to
   count top-level declarations.
3. `grep -nE '^(interface|type |const [A-Z]|function [A-Z])'` to list
   candidate extraction points.
4. `grep -n 'useState\|useEffect\|useMemo\|useCallback\|useRef'` to
   locate the hook surface -- these belong in the orchestrator or in a
   dedicated custom hook file.
5. `grep -nE 'fetchWithConfig\|customLogger\|api/' ` to map API calls.

### Phase 2 : PROPOSE boundaries

Sketch the target module layout. Apply these rules:

| Rule | Target file |
|---|---|
| Domain types / interfaces | `./{module}/types.ts` |
| Pure helper functions (parse, format, sort, group) | `./{module}/{module}Utils.ts` |
| Data-fetch + mutation logic called from the orchestrator | `./{module}/use{Module}Actions.ts` (custom hook) |
| A presentational sub-component that renders a row / card / tab | `./{module}/{Module}{SubName}.tsx` |
| A shared chip / badge used in multiple sub-components | `./{module}/{Module}{SmallName}.tsx` |
| Constants / enums / config tables | `./{module}/constants.ts` or inside `types.ts` |

The orchestrator keeps:
- `useState` / `useEffect` for top-level state
- Fetch orchestration (calling the custom hook)
- Top-level `<Box>` / `<Paper>` layout + `<Tabs>`
- Pagination wrapper
- HelpButton wiring

Aim for an orchestrator between 200 and 380 LOC. If it ends up above,
split further.

### Phase 3 : BOOTSTRAP the new tree

```bash
MODULE_DIR="sigma-react-frontend/src/components/{parent}/{module}"
mkdir -p "$MODULE_DIR"
```

For Go:

```bash
PKG_DIR="pkg/{parent}/{module}"
mkdir -p "$PKG_DIR"
```

Create files in order of dependency (leaf first): `types.ts` -> helpers
-> presentation -> custom hook -> orchestrator. Each creation is a
small, compilable step. Run `npx tsc --noEmit` (or `go build`) after
each step to catch regressions immediately.

### Phase 4 : HOOK ORDERING (critical)

When moving state from orchestrator-monolith into orchestrator-slim,
enforce this ordering in the orchestrator:

```
1. All `useState` declarations (group at the top of the body)
2. Any derived `const filterKey = ...` computation
3. Any `useMemo` / `useCallback`
4. `useEffect` for initial load
5. Custom hook invocation (e.g. useNis2Actions)
6. Derived render data (pagination, filters applied)
7. Early-return loading / error branches
8. JSX return
```

This explicit ordering closes the TDZ class of bugs. A `const filterKey
= f(applicabilityFilter)` that sits above `const [applicabilityFilter,
setApplicabilityFilter] = useState(...)` in the source IS a TDZ waiting
to crash in minified production bundles.

### Phase 5 : R17 fixture + test

For each file that touches an API (the orchestrator, or a sub-component
with its own fetch), create:

- `__fixtures__/{OrchestratorName}.fixture.json` (real shape or captured
  via curl if auth permits)
- `__tests__/{OrchestratorName}.test.tsx` with at least:
  1. fixture shape sanity (asserts every key the code reads)
  2. render without crashing with the fixture
  3. fetchWithConfig called with the expected URL
  4. fallback branch covered if applicable
  5. empty-data branch covered if applicable

Run `npx vitest run {path}` to confirm all assertions pass before
continuing.

### Phase 6 : COMMIT + CLEANUP

1. Remove the `// @allow-long-file` marker if present -- the file is
   now under the ceiling.
2. Stage only the new module tree + the shrunk orchestrator + the
   fixture + the test (avoid embarking unrelated files).
3. Commit with the `refactor(scope): split X into orchestrator + N
   presentation files` convention, mentioning:
   - LOC delta (1138 -> 334, for example)
   - Bug class closed (TDZ, coupling, etc.)
   - Test count (vitest 4/4 green)
   - File that carried the prior `// @allow-long-file` marker (now removed)

## Decision matrix : when to NOT split

Sometimes a long file is the right answer. Do not split when:

- The file is a **generated artifact** (OpenAPI client, Prisma schema,
  protobuf output). Mark `// @allow-long-file -- generated by X` and move on.
- The file is a **single long switch/case** that maps opaque codes
  (CWE catalog, CVSS vectors, country codes). Splitting spreads a
  single table across multiple files without helping readability.
- The file is a **migration SQL** in `cmd/sigma_web/migrations/`. SQL
  migrations are intentionally monolithic and timestamped.
- The orchestrator after split would still be > 400 LOC. Recurse: split
  sub-components further before declaring the refactor done.

## Template artifacts

### Orchestrator skeleton (React)

```tsx
// Orchestrator for {Feature}. Owns data fetch + top-level state.
// Presentation delegated to sibling files under ./{module}/.

import React, { useEffect, useState, useMemo } from 'react';
import { Box, Paper, Tabs, Tab } from '@mui/material';
import { fetchWithConfig } from '../../config/apiConfig';
import customLogger from '../../utils/customLogger';
import HelpButton from '../common/HelpButton';

import type { {Feature}Item, {Feature}Filter } from './{module}/types';
import { parse{Feature}Response, filter{Feature}Items } from './{module}/{module}Utils';
import {Feature}Card from './{module}/{Feature}Card';
import {Feature}Toolbar from './{module}/{Feature}Toolbar';
import { use{Feature}Actions } from './{module}/use{Feature}Actions';

const {Feature}Page: React.FC = () => {
    // 1. useState FIRST
    const [items, setItems] = useState<{Feature}Item[]>([]);
    const [filter, setFilter] = useState<{Feature}Filter>('all');
    const [loading, setLoading] = useState(true);

    // 2. derived values AFTER useState
    const filtered = useMemo(() => filter{Feature}Items(items, filter), [items, filter]);

    // 3. load effect
    useEffect(() => {
        (async () => {
            const resp = await fetchWithConfig('/api/{module}/items');
            if (resp.ok) {
                const data = await resp.json();
                setItems(parse{Feature}Response(data));
            }
            setLoading(false);
        })();
    }, []);

    // 4. custom hook (actions)
    const { export: handleExport } = use{Feature}Actions({ items: filtered });

    // 5. early returns
    if (loading) return <Box>Loading...</Box>;

    // 6. render
    return (
        <Box>
            <Paper>
                <{Feature}Toolbar filter={filter} onChange={setFilter} />
            </Paper>
            {filtered.map((item) => (
                <{Feature}Card key={item.id} item={item} />
            ))}
        </Box>
    );
};

export default {Feature}Page;
```

### Helpers file skeleton

```ts
// Pure helpers for {Feature}. No side effects, fully unit-testable.

import type { {Feature}Item, {Feature}Filter } from './types';

export function parse{Feature}Response(data: unknown): {Feature}Item[] {
    // ...
}

export function filter{Feature}Items(
    items: {Feature}Item[],
    filter: {Feature}Filter,
): {Feature}Item[] {
    // ...
}
```

### Custom hook skeleton

```ts
// useXxxActions -- encapsulates assessment / export / sync actions
// so the orchestrator stays focused on rendering.

import { useState, useCallback } from 'react';
import { fetchWithConfig } from '../../../config/apiConfig';
import customLogger from '../../../utils/customLogger';

export function use{Feature}Actions(opts: { items: {Feature}Item[] }) {
    const [syncing, setSyncing] = useState(false);

    const export: () => Promise<void> = useCallback(async () => {
        // ...
    }, [opts.items]);

    const sync: () => Promise<void> = useCallback(async () => {
        setSyncing(true);
        try {
            // ...
        } finally {
            setSyncing(false);
        }
    }, []);

    return { syncing, export, sync };
}
```

## Go variant

For Go files above 800 LOC, the split pattern is:

```
pkg/{module}/
  types.go         // domain types
  {module}_service.go       // interface + main service impl (orchestrator)
  {module}_loader.go        // data ingestion helpers
  {module}_repository.go    // PostgreSQL queries (sql.Rows scanning)
  {module}_api.go           // http.HandlerFunc registrations
  {module}_api_handlers.go  // individual handlers
  {module}_test.go          // table-driven tests
  {module}_repository_test.go
```

Apply the same rules: loaders + repo are leaf-first, service is the
orchestrator, API file is a thin Register function + handlers.

## Integration with other skills

| After /refactor-long-file | Next skill | Why |
|---|---|---|
| Refactor delivered | `/test-first` | Ensure each new module has a test |
| Refactor delivered | `/verify-fix` | R17 render verifies fixture + bundle in prod |
| Tests green | `/react-recette` or `/go-recette` | Anti-pattern scan on the new tree |
| All green | Commit + push | Done |

## Tracing

Each refactor writes:

- `_alire/tracking/PLAN_REFACTOR_{module}_{YYYY-MM-DD}.md` with the
  proposed split + rationale
- `_alire/02_LOGS/Journals/decision_log.jsonl` with a `REFACTOR_SPLIT`
  entry citing the bug class closed
- `_alire/02_LOGS/Journals/retex/RETEX_REFACTOR_{module}_{date}.md`
  with LOC delta, test count, rollback instructions

## Anti-patterns (forbidden)

- Splitting into files that each contain a single 3-line function
  (over-decomposition; aim for 80-250 LOC per presentation file)
- Creating a `*_helpers.ts` dumping ground -- name the file for the
  domain concept it serves (`nis2Utils.ts`, not `utils.ts`)
- Moving state out of the orchestrator into the presentation (creates
  prop-drilling instead of coupling reduction)
- Committing the orchestrator shrink without the new tree (broken
  build) -- stage and commit atomically
- Leaving `// @allow-long-file` on the orchestrator "just in case"
- Skipping the R17 fixture + test for the orchestrator after split
  (the split itself doesn't close R17 gate, the tests do)

## Precedent : Nis2ByArticles (2026-04-24, commit 11debc02c0)

| Metric | Before | After |
|---|---|---|
| Monolithic LOC | 1145 | 334 (orchestrator) |
| Files | 1 | 10 (orchestrator + 9 modules) |
| Largest module | 1145 | 208 (nis2Utils.ts) |
| Tests | 0 | 4 (vitest 4/4 PASS) |
| `// @allow-long-file` markers | 1 | 0 |
| TDZ bug class (hook ordering) | open | closed |
| Bundle TDZ crash in prod | yes ("Cannot access 'C' before initialization") | no |

Reference : `pdca/nis2-by-articles/cycle_001/` and
`_alire/02_LOGS/Journals/retex/RETEX_PDCA_NIS2_BY_ARTICLES_2026-04-24.md`.
