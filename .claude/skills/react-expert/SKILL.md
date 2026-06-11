---
name: react-expert
description: Use when building React 18+ / 19 components, custom hooks, Server Components (Next.js App Router), Suspense boundaries, useActionState forms, performance optimization, or migrating class components to functional. Invoke for .jsx / .tsx work, state management (Context, Zustand, Redux, TanStack Query), or React 19 features. Adapted for LIA-SEC conventions (MUI v7 Grid, fetchWithConfig, customLogger, theme-aware styling).
license: MIT (upstream), adapted for LIA-SEC
metadata:
  author: https://github.com/Jeffallan (upstream), LIA-SEC adaptation by mo0ogly
  version: "1.1.0-liasec"
  domain: frontend
  triggers: React, JSX, hooks, useState, useEffect, useContext, Server Components, React 19, Suspense, TanStack Query, Redux, Zustand, component, frontend, MUI, sigma-react-frontend
  role: specialist
  scope: implementation
  output-format: code
  related-skills: react-recette, debug-react, frontend-design, react-best-practices, react-useeffect, test-first, api-handoff
---

# React Expert (LIA-SEC Edition)

Senior React specialist with deep expertise in React 19, Server Components, and
production-grade application architecture -- adapted for the LIA-SEC frontend
stack (`sigma-react-frontend/`, React 19 + TypeScript 4.9 + MUI v7 + Vite).

## When to Use This Skill

- Building a new `.tsx` component in `sigma-react-frontend/src/components/`
- Implementing custom hooks (`useWatch*`, `useFetch*`, `useThrottle*`)
- Implementing state management (Context, Zustand, Redux, TanStack Query)
- Optimizing React performance (memo, lazy, virtualization, Suspense)
- React 19 features (useActionState, `use()` hook, server components)
- Migrating class components to functional + hooks
- Forms (with MUI + React 19 actions)
- Data fetching (TanStack Query, `use()` hook, SWR)

## When NOT to Use This Skill

- Pure validation / lint -> use `/react-recette`
- Debugging a runtime crash -> use `/debug-react`
- Creative UI / visual design -> use `/frontend-design`
- Performance tuning via Vercel patterns -> use `react-best-practices`
- Enforcing tests -> `/test-first` will wrap the output
- Backend -> frontend contract -> use `/api-handoff` BEFORE writing the component

## Core Workflow

1. **Analyze requirements** -- identify component hierarchy, state needs, data flow
2. **Check the contract** -- if the component calls an API, ensure a fixture exists
   (R17 Frontend Contract Gate). If not, run `/api-handoff {feature} --r17` FIRST.
3. **Choose patterns** -- pick state management, data fetching approach
4. **Implement** -- TypeScript + MUI v7 + fetchWithConfig + customLogger
5. **Validate** -- `cd sigma-react-frontend && npx tsc --noEmit`; iterate until clean
6. **Optimize** -- memoize callbacks/objects passed to memoized children
7. **Test** -- Vitest + React Testing Library; run until green
8. **Integrate** -- add `<HelpButton>` if new screen/tab; verify parent import
   (see R17 + feedback_check_component_integration)
9. **Document** -- update the matching `.md` in `_alire/01_DOCUMENTATION/`
   (R15 + R20 -- docs updated in the SAME pass as the code)

Every step gated by the Verification Gate (below). The 9-step workflow maps onto
APEX's OODA loop (OBSERVE steps 1-2, ORIENT 3, DECIDE 3, ACT 4-9).

## Decomposition des sous-taches

Au demarrage, decomposer toute demande en sous-taches independantes :

- [ ] Sous-tache 1 : reads / greps pour cartographier le composant + son parent + le contrat API
- [ ] Sous-tache 2 : verifier/capturer la fixture R17 (`/api-handoff {feature} --r17` si absente)
- [ ] Sous-tache 3 : choix patterns (state mgmt, data fetching) + types TS
- [ ] Sous-tache 4 : implementation .tsx + service `.ts` (unwrap `{success,data}`)
- [ ] Sous-tache 5 : test render-and-assert (Vitest + RTL) sur la fixture
- [ ] Sous-tache 6 : HelpButton + `/create-ui-help` + verif import parent + tsc + build

Utiliser `TaskCreate` pour tracker si > 3 sous-taches.

## Plan d'execution

Pour tout composant/feature non trivial (> 3 fichiers ou nouvel ecran/tab) :

1. Creer `_alire/tracking/PLAN_REACT_EXPERT_{FEATURE}_{YYYY-MM-DD}.md` avant d'ecrire une ligne.
2. Template : `_alire/tracking/PLAN_TEMPLATE.md`.
3. Cocher chaque sous-tache a la completion.
4. Si replanification : Status -> REPLANIFIE + lien vers nouveau plan.

Pour une modification ponctuelle (1 composant, pas d'API) : plan inline suffit.

## Adaptation et replanification

Si 2 etapes consecutives echouent :

- STOP -> invoquer `/replan` -> produit `PLAN_REACT_EXPERT_*_REPLAN_*.md` -> NE PAS improviser.

Declencheurs typiques :
- `tsc` echoue apres fix -> REPLAN
- Test render casse apres refactor -> REPLAN
- Fixture ne matche pas le contrat live (R17) -> REPLAN (re-capturer via `/api-handoff` ou `lia_capture_fixture`)
- Composant illisible sur 1+ theme (WCAG R31) -> REPLAN

## Outils declares

| Outil | Usage | Retry policy |
|-------|-------|--------------|
| `Read`, `Grep`, `Glob` | Cartographier composant + parent + contrat avant d'ecrire | N/A |
| `Write`, `Edit` | Creer/modifier .tsx / .ts | N/A |
| `Bash npx tsc --noEmit` | Type-check (gate) | echec -> diagnose |
| `Bash vp test run` (vite-plus 0.1.24) | Tests Vitest+RTL -- JAMAIS `npx vitest` direct (faux TDZ) | 1 retry flakiness |
| `Bash` build (`vp build` / vite build) | Build gate | echec -> diagnose, pas de retry aveugle |
| `lia_capture_fixture` | Capturer fixture R17 contre backend live (JWT forge) | N/A |
| `TaskCreate` | Tracking si > 3 sous-taches | N/A |
| `Skill(api-handoff)` | AVANT composant API (contrat + fixture) | Obligatoire si API |
| `Skill(create-ui-help)` | Nouvel ecran/tab | Obligatoire |
| `Skill(test-first)` / `Skill(react-recette)` | Tests / audit avant commit | Obligatoire |
| `Skill(frontend-design)` | Audit WCAG 6 themes (R31) | Obligatoire si rendu colore |

Selection dynamique : outil choisi selon le contexte, pas de liste figee.

## Tracabilite agentique

Logger dans `_alire/02_LOGS/Journals/decision_log.jsonl` chaque decision non triviale :

- Choix de state management (Context vs Zustand vs TanStack) + pourquoi
- Choix data-fetching (`use()` vs useEffect vs SWR)
- Rejet d'une alternative + trade-off (perf vs lisibilite)

Format :
```json
{"timestamp":"...","session":"react-expert-{feature}","action":"...","reasoning":"...","alternatives_rejected":["..."],"outcome":"...","confidence":"high","plan_ref":"PLAN_REACT_EXPERT_*.md"}
```

RETEX en fin de session si score agentique < 40/50 -> `_alire/02_LOGS/Journals/retex/RETEX_REACT_EXPERT_YYYY-MM-DD.md`.

## Reference Guide

Load detailed guidance based on context:

| Topic | Reference | Load When |
|-------|-----------|-----------|
| Server Components | `references/server-components.md` | RSC patterns, Next.js App Router (rare in LIA-SEC) |
| React 19 | `references/react-19-features.md` | use() hook, useActionState, forms |
| State Management | `references/state-management.md` | Context, Zustand, Redux, TanStack |
| Hooks | `references/hooks-patterns.md` | Custom hooks, useEffect, useCallback |
| Performance | `references/performance.md` | memo, lazy, virtualization |
| Testing | `references/testing-react.md` | Testing Library, mocking |
| Class Migration | `references/migration-class-to-modern.md` | Converting class components to hooks/RSC |

## LIA-SEC Adaptations (MANDATORY)

Everything in the upstream skill applies, PLUS these rules drawn from
`.claude/rules/enforcement-frontend.md`, `anti-patterns.md`, and R17 / R21 / R23.

### 1. API calls -- fetchWithConfig only

```tsx
// CORRECT
import { fetchWithConfig } from '../config/apiConfig';
const response = await fetchWithConfig('/api/ai/models');

// For download URLs / websocket / anything needing the raw base URL
import { getBackendUrl } from '../../services/ConfigurationService';
const url = `${getBackendUrl()}/api/download/file`;
```

```tsx
// FORBIDDEN -- 401 systematique on protected endpoints
const response = await fetch('/api/ai/models');
const response = await fetch(`${API_BASE_URL}/api/...`);
```

### 2. Service-layer envelope unwrap (R17)

Backend returns `{success, data}` envelopes. Services MUST unwrap `.data`.

```ts
// CORRECT
export async function getProviderStatus(): Promise<ProviderStatus> {
  const resp = await fetchWithConfig('/api/ai/fallback/status');
  const body = await resp.json();
  if (!body.success) throw new Error(body.error || 'API error');
  return body.data as ProviderStatus;
}

// FORBIDDEN
return resp.json(); // leaks the envelope to the component
```

### 3. MUI v7 Grid syntax

```tsx
// CORRECT
<Grid size={{ xs: 12, md: 8 }}>

// FORBIDDEN (MUI v5/v6 -- breaking change)
<Grid item xs={12} md={8}>
```

### 4. Logging -- customLogger only (R6)

```tsx
// CORRECT
import { customLogger } from '../../services/loggerService';
customLogger.info('COMPONENT', 'Fetching data', { endpoint });

// FORBIDDEN
console.log('...');
console.error('...');
```

### 5. Theme-aware styling (no hardcoded hex, no hardcoded fonts)

```tsx
// CORRECT
fontFamily: 'inherit'  // inherits from active theme
color: theme.palette.error.main
backgroundColor: alpha(theme.palette.warning.main, 0.15)
import { BRAND, CVE_SEVERITY } from '../constants/colors';
bgcolor: BRAND.AZURE_PRIMARY

// FORBIDDEN
fontFamily: '"Fira Code", monospace'
color: '#ff0000'
```

### 5bis. Semantic color props + WCAG contract (R31 -- MANDATORY)

A theme token is NOT a WCAG guarantee. `color: theme.palette.info.main` passes the
"no-hardcoded-hex" gate yet can fail AA contrast on some themes. Two rules:

```tsx
// CORRECT -- semantic color prop routes through the theme MuiChip/MuiButton override,
// which is THE single source of contrast truth (fix once per theme, app-wide).
<Chip color="info" />
<Chip color="error" variant="outlined" />
<Button color="info" variant="contained" />

// FORBIDDEN -- bypasses the MuiChip override AND resolves to an unset palette.X.contrastText
// (MUI auto-picks white -> fails AA on mid-tone info/error). Caused the 2026-05-24 EUVD rework.
<Chip sx={{ bgcolor: 'info.main', color: 'info.contrastText' }} />
<Chip sx={{ bgcolor: theme.palette.error.main, color: theme.palette.error.contrastText }} />
```

- For chips/buttons: ALWAYS the `color="info|error|warning|success|primary"` prop, never
  `sx bgcolor:'X.main'`. Fix contrast in the theme `MuiChip.color{X}` override / palette
  `contrastText`, never with per-component `info.dark` / `getContrastText` hacks.
- A colored token used as TEXT/ICON on a tinted/non-default background (`color:
  theme.palette.info.main` on a light Paper) MUST have its contrast verified across the 6
  themes; if it fails, the readable value comes from the theme palette calibration, not a
  per-component workaround.
- "Done" requires the 6-theme WCAG audit (`/frontend-design`, run in `/apex` Phase 4b-bis
  and `/audit-pdca` C.2bis). A pipeline-green but WCAG-unverified `.tsx` is NOT done.

Reference: `.claude/rules/theme-token-not-wcag.md` (R31), `.claude/rules/no-hardcoded-colors-in-tsx.md` (R25).

### 6. Rectangular chips (feedback_no_oval_badges)

```tsx
<Chip sx={{ borderRadius: 1 }} />  // rectangular pro look, never oval
```

### 7. Dialog no truncation (R21)

Any Dialog with variable-length content:
```tsx
<Dialog maxWidth="lg" fullWidth PaperProps={{ sx: { maxHeight: '90vh' } }}>
  <DialogContent sx={{ overflow: 'auto' }}>
    {/* content */}
  </DialogContent>
</Dialog>
```

### 8. Charts -- external labels (R23)

For any radar / bubble / pie with 4+ marks: use `angularExternalLabels` from
`components/grc/shared/radarUtils.ts`, reserve `margin >= 130` for labels.
Never place labels inline next to crowded marks.

### 9. R17 Frontend Contract Gate (BLOCKING)

Any component calling an API MUST:
1. Have a captured fixture in `__fixtures__/{component}.fixture.json`
2. Have a render-and-assert test (Vitest + RTL)
3. Pass a Playwright smoke test post-deploy
4. Unwrap `{success, data}` at the service layer

Cycle cannot close without R17 evidence.

### 10. HelpButton on new screens (R8)

Every new screen/tab MUST have a `<HelpButton component="..." tabKey="..." />`
and a corresponding row in the PostgreSQL `ui_help_content` table (English
content mandatory). Use `/create-ui-help` BEFORE adding the button. Never
ship a HelpButton pointing at an empty row.

### 11. Parent import check (feedback_check_component_integration)

After creating a new `.tsx`, GREP to confirm a parent actually imports it.
A component without a consumer is dead code and will be missed in testing.

## Key Patterns

### Server Component (Next.js App Router -- rare in LIA-SEC)
```tsx
// app/users/page.tsx - Server Component, no "use client"
import { db } from '@/lib/db';

interface User {
  id: string;
  name: string;
}

export default async function UsersPage() {
  const users: User[] = await db.user.findMany();
  return (
    <ul>
      {users.map((user) => (
        <li key={user.id}>{user.name}</li>
      ))}
    </ul>
  );
}
```

### React 19 Form with useActionState
```tsx
'use client';
import { useActionState } from 'react';

async function submitForm(_prev: string, formData: FormData): Promise<string> {
  const name = formData.get('name') as string;
  return `Hello, ${name}!`;
}

export function GreetForm() {
  const [message, action, isPending] = useActionState(submitForm, '');
  return (
    <form action={action}>
      <input name="name" required />
      <button type="submit" disabled={isPending}>
        {isPending ? 'Submitting...' : 'Submit'}
      </button>
      {message && <p>{message}</p>}
    </form>
  );
}
```

### Custom Hook with Cleanup
```tsx
import { useState, useEffect } from 'react';

function useWindowWidth(): number {
  const [width, setWidth] = useState(() => window.innerWidth);

  useEffect(() => {
    const handler = () => setWidth(window.innerWidth);
    window.addEventListener('resize', handler);
    return () => window.removeEventListener('resize', handler);
  }, []);

  return width;
}
```

### LIA-SEC typical component skeleton

```tsx
import React, { useEffect, useState } from 'react';
import { Box, Paper, Typography, Chip, CircularProgress } from '@mui/material';
import { fetchWithConfig } from '../../config/apiConfig';
import { customLogger } from '../../services/loggerService';
import HelpButton from '../common/HelpButton';
import AIMarkdownView from '../common/AIMarkdownView';

interface ProviderStatus {
  provider: string;
  healthy: boolean;
  latencyMs: number;
}

export default function AIStatusPanel(): JSX.Element {
  const [status, setStatus] = useState<ProviderStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const resp = await fetchWithConfig('/api/ai/fallback/status');
        const body = await resp.json();
        if (!body.success) throw new Error(body.error || 'API error');
        if (!cancelled) setStatus(body.data as ProviderStatus);
      } catch (e) {
        const msg = e instanceof Error ? e.message : 'unknown error';
        customLogger.error('AI_STATUS', 'Failed to fetch', { error: msg });
        if (!cancelled) setError(msg);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  if (loading) return <CircularProgress />;
  if (error) return <Typography color="error">{error}</Typography>;
  if (!status) return <Typography>No status available</Typography>;

  return (
    <Paper sx={{ p: 2 }}>
      <Box display="flex" alignItems="center" gap={1}>
        <Typography variant="h6">AI Provider</Typography>
        <HelpButton component="ai_status" tabKey="overview" />
      </Box>
      <Chip
        label={status.provider}
        color={status.healthy ? 'success' : 'error'}
        sx={{ borderRadius: 1, mt: 1 }}
      />
      <Typography variant="body2" sx={{ mt: 1, fontFamily: 'inherit' }}>
        Latency: {status.latencyMs} ms
      </Typography>
    </Paper>
  );
}
```

## Constraints

### MUST DO
- TypeScript strict mode
- Error boundaries for graceful failures
- Stable, unique `key` props (never array index for dynamic lists)
- useEffect cleanup functions (prevent memory leaks)
- Semantic HTML + ARIA
- Memoize callbacks/objects passed to memoized children
- Suspense for async operations
- **LIA-SEC**: fetchWithConfig, customLogger, MUI v7 Grid, theme-aware styling,
  HelpButton, R17 gate, parent-import check

### MUST NOT DO
- Mutate state directly
- Create functions inside JSX (causes re-renders)
- Skip error boundaries in production
- Ignore React strict mode warnings
- **LIA-SEC**: hardcode `http://localhost:8081`, `fetch()` brut, `console.log`,
  hex colors, `monospace`, `<Grid item>`, oval chips, HelpButton pointing to
  empty `ui_help_content`

## Output Templates

When implementing React features, provide:
1. Component `.tsx` file with TypeScript types + MUI v7 + HelpButton
2. Service `.ts` file unwrapping `{success, data}` envelope
3. Fixture file `__fixtures__/{component}.fixture.json` (captured via curl)
4. Vitest + RTL test using the fixture
5. UI help entry (`/create-ui-help`) if new screen/tab
6. Doc update in `_alire/01_DOCUMENTATION/` if API contract changed (R15 + R20)
7. Brief explanation of key decisions + evolutions possibles (BLOC 9)

## Knowledge Reference

React 19, Server Components, use() hook, Suspense, TypeScript, TanStack Query,
Zustand, Redux Toolkit, React Router, React Testing Library, Vitest/Jest,
Next.js App Router, accessibility (WCAG), MUI v7, Vite, LIA-SEC conventions
(R5, R6, R8, R12, R17, R21, R23, enforcement-frontend).

## VERIFICATION GATE (BLOQUANT)

Apres execution, AVANT de declarer termine :

- [ ] `cd sigma-react-frontend && npx tsc --noEmit` clean (zero NEW error)
- [ ] `vp test run <test>` vert (vite-plus 0.1.24 -- JAMAIS `npx vitest` direct)
- [ ] Build passe (`vp build` / vite build) -- pas de regression bundle
- [ ] R17 : fixture capturee + test render-and-assert + service unwrap `.data`
- [ ] Nouvel ecran/tab -> `<HelpButton>` + row `ui_help_content` (R8)
- [ ] Composant importe par un parent (feedback_check_component_integration)
- [ ] WCAG AA verifie sur les 6 themes si rendu colore (R31, `/frontend-design`)
- [ ] Smoke test live post-deploy si outward-facing (R26)

Si un gate echoue : STOP, fix, re-gate. JAMAIS declarer "done" avec un gate rouge.

## Scoring agentique

| Critere | Score |
|---------|-------|
| C1 Decomposition : sous-taches identifiees ? | /10 |
| C2 Planification : PLAN_*.md cree et suivi ? | /10 |
| C3 Replanification : /replan declenche sur echecs consecutifs ? | /10 |
| C4 Outillage : outils choisis dynamiquement + api-handoff/test-first/react-recette invoques ? | /10 |
| C5 Tracabilite : decision_log + RETEX produits ? | /10 |

Score total /50 -- >= 40 : Exemplaire | 30-39 : Acceptable | < 30 : RETEX obligatoire
