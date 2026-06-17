---
name: react-expert
description: Use when building React 18+ / 19 components, custom hooks, Server Components (Next.js App Router), Suspense boundaries, useActionState forms, performance optimization, or migrating class components to functional. Invoke for .jsx / .tsx work, state management (Context, Zustand, Redux, TanStack Query), or React 19 features. Adapted for inspect_ia_agents conventions (typed fetch client, R16 contract gate, theme-aware CSS tokens, no hardcoded colors).
license: MIT (upstream), adapted for inspect_ia_agents
metadata:
  author: https://github.com/Jeffallan (upstream), inspect_ia_agents adaptation
  version: "1.1.0-inspect_ia_agents"
  domain: frontend
  triggers: React, JSX, hooks, useState, useEffect, useContext, Server Components, React 19, Suspense, TanStack Query, Redux, Zustand, component, frontend, console, console
  role: specialist
  scope: implementation
  output-format: code
  related-skills: react-recette, frontend-design, react-best-practices, test-first
---

# React Expert (inspect_ia_agents Edition)

Senior React specialist with deep expertise in React 19, Server Components, and
production-grade application architecture -- adapted for the inspect_ia_agents
approval/audit console (`console/`, React 18 + TypeScript +
Vite, theme-aware CSS tokens, no UI-kit lock-in).

## When to Use This Skill

- Building a new `.tsx` component in `console/src/components/`
  or a page under `console/src/pages/`
- Implementing custom hooks (`useRunSocket`, `useAuditEvents`, `useThrottle*`)
- Implementing state management (Context, Zustand, Redux, TanStack Query)
- Optimizing React performance (memo, lazy, virtualization, Suspense)
- React 19 features (useActionState, `use()` hook, server components)
- Migrating class components to functional + hooks
- Forms (React 19 actions)
- Data fetching (the typed `request<T>` client, TanStack Query, `use()` hook, SWR)

## When NOT to Use This Skill

- Pure validation / lint -> use `/react-recette`
- Creative UI / visual design -> use `/frontend-design`
- Performance tuning via Vercel patterns -> use `react-best-practices`
- Enforcing tests -> `/test-first` will wrap the output

## Core Workflow

1. **Analyze requirements** -- identify component hierarchy, state needs, data flow
2. **Check the contract** -- if the component calls an API, ensure a fixture exists
   (R16 Frontend Contract Gate). If not, capture one against the live API FIRST.
3. **Choose patterns** -- pick state management, data fetching approach
4. **Implement** -- TypeScript + the typed `request<T>` client + theme-aware CSS tokens
5. **Validate** -- `cd console && node node_modules/.bin/tsc --noEmit`; iterate until clean
6. **Optimize** -- memoize callbacks/objects passed to memoized children
7. **Test** -- Vitest + React Testing Library; run until green
8. **Integrate** -- verify a parent actually imports the new component
   (R16 + component-integration check)
9. **Document** -- update the matching tracking note under `docs/tracking/`
   (R25 -- tracking stays in the gitignored `docs/tracking/`)

Every step gated by the Verification Gate (below). The 9-step workflow maps onto
APEX's OODA loop (OBSERVE steps 1-2, ORIENT 3, DECIDE 3, ACT 4-9).

## Decomposition des sous-taches

Au demarrage, decomposer toute demande en sous-taches independantes :

- [ ] Sous-tache 1 : reads / greps pour cartographier le composant + son parent + le contrat API
- [ ] Sous-tache 2 : verifier/capturer la fixture R16 (capture live contre l'API si absente)
- [ ] Sous-tache 3 : choix patterns (state mgmt, data fetching) + types TS
- [ ] Sous-tache 4 : implementation .tsx + service `.ts` (unwrap l'enveloppe si l'endpoint en a une)
- [ ] Sous-tache 5 : test render-and-assert (Vitest + RTL) sur la fixture
- [ ] Sous-tache 6 : verif import parent + tsc + build

Utiliser `TaskCreate` pour tracker si > 3 sous-taches.

## Plan d'execution

Pour tout composant/feature non trivial (> 3 fichiers ou nouvel ecran/page) :

1. Creer `docs/tracking/PLAN_REACT_EXPERT_{FEATURE}_{YYYY-MM-DD}.md` avant d'ecrire une ligne.
2. Cocher chaque sous-tache a la completion.
3. Si replanification : Status -> REPLANIFIE + lien vers nouveau plan.

Pour une modification ponctuelle (1 composant, pas d'API) : plan inline suffit.

## Adaptation et replanification

Si 2 etapes consecutives echouent :

- STOP -> invoquer `/replan` -> produit `PLAN_REACT_EXPERT_*_REPLAN_*.md` -> NE PAS improviser.

Declencheurs typiques :
- `tsc` echoue apres fix -> REPLAN
- Test render casse apres refactor -> REPLAN
- Fixture ne matche pas le contrat live (R16) -> REPLAN (re-capturer la fixture)
- Composant illisible sur 1+ theme (WCAG) -> REPLAN

## Outils declares

| Outil | Usage | Retry policy |
|-------|-------|--------------|
| `Read`, `Grep`, `Glob` | Cartographier composant + parent + contrat avant d'ecrire | N/A |
| `Write`, `Edit` | Creer/modifier .tsx / .ts | N/A |
| `Bash node node_modules/.bin/tsc --noEmit` | Type-check (gate) | echec -> diagnose |
| `Bash npx vitest run` | Tests Vitest+RTL | 1 retry flakiness |
| `Bash node node_modules/.bin/vite build` | Build gate | echec -> diagnose, pas de retry aveugle |
| `TaskCreate` | Tracking si > 3 sous-taches | N/A |
| `Skill(frontend-design)` | Audit WCAG multi-themes | Obligatoire si rendu colore |
| `Skill(test-first)` / `Skill(react-recette)` | Tests / audit avant commit | Obligatoire |

Selection dynamique : outil choisi selon le contexte, pas de liste figee.

## Tracabilite agentique

Logger dans `docs/tracking/decision_log.jsonl` chaque decision non triviale :

- Choix de state management (Context vs Zustand vs TanStack) + pourquoi
- Choix data-fetching (`use()` vs useEffect vs SWR)
- Rejet d'une alternative + trade-off (perf vs lisibilite)

Format :
```json
{"timestamp":"...","session":"react-expert-{feature}","action":"...","reasoning":"...","alternatives_rejected":["..."],"outcome":"...","confidence":"high","plan_ref":"PLAN_REACT_EXPERT_*.md"}
```

RETEX en fin de session si score agentique < 40/50 -> `docs/tracking/retex/RETEX_REACT_EXPERT_YYYY-MM-DD.md`.

## Reference Guide

Load detailed guidance based on context:

| Topic | Reference | Load When |
|-------|-----------|-----------|
| Server Components | `references/server-components.md` | RSC patterns, Next.js App Router (rare in the console) |
| React 19 | `references/react-19-features.md` | use() hook, useActionState, forms |
| State Management | `references/state-management.md` | Context, Zustand, Redux, TanStack |
| Hooks | `references/hooks-patterns.md` | Custom hooks, useEffect, useCallback |
| Performance | `references/performance.md` | memo, lazy, virtualization |
| Testing | `references/testing-react.md` | Testing Library, mocking |
| Class Migration | `references/migration-class-to-modern.md` | Converting class components to hooks/RSC |

## inspect_ia_agents Adaptations (MANDATORY)

Everything in the upstream skill applies, PLUS these rules drawn from the
project's frontend contract gate (R16) and the no-hardcoded-colors / no-emoji
conventions (R10, R25).

### 1. API calls -- the typed `request<T>` client only

The console talks to the Rust Axum gateway through a single typed client
(`src/api/client.ts`). The base URL comes from the environment (R5); the
`localhost` value is only a dev fallback set by `recette.sh` (R19).

```tsx
// CORRECT -- call a typed wrapper from the client; never assemble a URL by hand
import { listPendingApprovals } from "../../api/client";
const pending = await listPendingApprovals();

// For a WebSocket / SSE / download, use the client's URL helpers
import { openRunSocket, realtimeStreamUrl } from "../../api/client";
const socket = openRunSocket(runId);
const source = new EventSource(realtimeStreamUrl());
```

```tsx
// FORBIDDEN -- hardcoded host / raw fetch in a component bypasses typing,
// the env base URL (R5) and the canonical port wiring (R19)
const res = await fetch("http://localhost:8090/approvals");
const res = await fetch(`${API_BASE_URL}/audit/events`);
```

### 2. Service-layer envelope unwrap (R16)

R16: a component that calls an API MUST unwrap the response envelope at the
service layer and never leak it into the component. Most inspect_ia_agents
endpoints answer with a raw object OR a single wrapper key (e.g. `{events: []}`,
`{pending: []}`, `{actions, count}`); the client unwraps that key for you.
When an endpoint DOES carry a `{success, data}` envelope, unwrap `.data`
explicitly and surface `error` -- never return the raw body.

```ts
// CORRECT -- unwrap the wrapper key (the client does this for list routes)
export function listPendingApprovals(): Promise<PendingApproval[]> {
  return request<{ pending: PendingApproval[] }>("/approvals?state=pending", {
    method: "GET",
  }).then((res) => res.pending);
}

// CORRECT -- explicit unwrap when an endpoint uses a success/data envelope
export async function getThing(): Promise<Thing> {
  const body = await request<{ success: boolean; data: Thing; error?: string }>("/thing");
  if (!body.success) throw new Error(body.error ?? "API error");
  return body.data;
}

// FORBIDDEN -- leaking the envelope / wrapper to the component
return request("/approvals?state=pending"); // component now sees {pending: ...}
```

### 3. Discriminated-union states -- cover every variant (R16)

For any component rendering an `approval_state` or a `policy_decision`, the
render-and-assert test MUST cover every variant of the discriminated union:
`approval_state ∈ {none, pending, approved, denied, timeout}` and
`policy_decision ∈ {allow, deny, escalate}`. An unhandled variant is a display
bug in production. The approval fixtures already exist
(`src/pages/approvals/__fixtures__/{pending,approved-outcome,denied-outcome}.fixture.json`).

```tsx
// CORRECT -- exhaustive switch, no silent fallthrough
function decisionLabel(d: PolicyDecision): string {
  switch (d) {
    case "allow": return "Allowed";
    case "deny": return "Denied";
    case "escalate": return "Escalated";
    // a new variant fails the type check here -> caught at compile time
  }
}
```

### 4. Logging -- no debug console output shipped (R6/R10)

The console ships no `console.log`/`console.error` debug noise. Surface errors in
the UI (an error state, a banner), and let real failures throw through the typed
client's `ApiError`. Do not leave `console.*` debug calls in committed code.

```tsx
// CORRECT -- error becomes UI state, no console noise
catch (e) {
  const msg = e instanceof Error ? e.message : "unknown error";
  setError(msg);
}

// FORBIDDEN -- debug noise shipped to prod
console.log("fetched", data);
console.error("oops", e);
```

### 5. Theme-aware styling (CSS tokens, no hardcoded hex, no hardcoded fonts)

The console is themed with CSS custom properties in `src/index.css` (a calibrated
neutral palette + a single deep-blue accent). Every page consumes tokens; a
hardcoded hex or font breaks theming and the no-hardcoded-colors rule (R25).

```tsx
// CORRECT -- consume a token, inherit the active theme's font
<div style={{ color: "var(--color-text)", background: "var(--color-surface)" }} />
<span style={{ color: "var(--color-accent)" }} />
// or via a className that resolves tokens in the page's .css

// FORBIDDEN -- hardcoded color / font defeats the theme tokens
<div style={{ color: "#1f4e79", fontFamily: '"Fira Code", monospace' }} />
```

### 5bis. Semantic state colors + WCAG contract

A raw color value is NOT a WCAG guarantee. Drive status colors through the shared
state tokens (e.g. `--color-success`, `--color-danger`, `--color-warning`) so
contrast is calibrated once per theme, app-wide -- never with a per-component hex.

- A colored token used as TEXT/ICON on a tinted surface MUST have its contrast
  verified across every theme; if it fails, the readable value comes from the
  token calibration in `src/index.css`, not a per-component workaround.
- "Done" requires the multi-theme WCAG audit (`/frontend-design`). A build-green
  but WCAG-unverified `.tsx` is NOT done.

### 6. Rectangular status chips

```tsx
// rectangular pro look, never oval -- drive radius from a token
<span className="chip" style={{ borderRadius: "var(--radius-sm)" }} />
```

### 7. Dialog / panel no truncation

Any modal or panel with variable-length content scrolls its body instead of
clipping it:
```tsx
<div className="modal" style={{ maxHeight: "90vh" }}>
  <div className="modal-body" style={{ overflow: "auto" }}>
    {/* content */}
  </div>
</div>
```

### 8. Charts -- external labels

For any radar / bubble / pie with 4+ marks: place labels OUTSIDE the plot and
reserve margin for them. Never crowd labels inline next to dense marks.

### 9. R16 Frontend Contract Gate (BLOCKING)

Any component calling an API MUST:
1. Have a captured fixture in `__fixtures__/{component}.fixture.json` (a REAL
   payload, captured from the live API -- not invented)
2. Have a render-and-assert test (Vitest + RTL) that asserts no runtime error
   and at least one expected DOM element
3. Unwrap the response envelope / wrapper key at the service layer
4. For `approval_state` / `policy_decision`: cover every discriminated-union variant

Cycle cannot close without R16 evidence.
Reference: `.claude/rules/frontend-contract-gate.md` (R16).

### 10. Parent import check (component-integration)

After creating a new `.tsx`, GREP to confirm a parent (a page, a router route,
or another component) actually imports it. A component without a consumer is dead
code and will be missed in testing.

## Key Patterns

### Server Component (Next.js App Router -- rare in the console)
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

### inspect_ia_agents typical component skeleton

```tsx
import React, { useEffect, useState } from "react";
import { listPendingApprovals } from "../../api/client";
import type { PendingApproval } from "../../types/platform";

export default function PendingApprovalsPanel(): JSX.Element {
  const [pending, setPending] = useState<PendingApproval[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const items = await listPendingApprovals(); // service unwraps {pending}
        if (!cancelled) setPending(items);
      } catch (e) {
        const msg = e instanceof Error ? e.message : "unknown error";
        if (!cancelled) setError(msg);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) return <p>Loading...</p>;
  if (error) return <p style={{ color: "var(--color-danger)" }}>{error}</p>;
  if (!pending || pending.length === 0) return <p>No pending approvals</p>;

  return (
    <section style={{ background: "var(--color-surface)", color: "var(--color-text)" }}>
      <h2>Pending approvals</h2>
      <ul>
        {pending.map((a) => (
          <li key={a.event_id}>
            <span
              className="chip"
              style={{ borderRadius: "var(--radius-sm)", color: "var(--color-accent)" }}
            >
              {a.approval_state}
            </span>{" "}
            {a.agent_id} -- {a.action_type}
          </li>
        ))}
      </ul>
    </section>
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
- **inspect_ia_agents**: typed `request<T>` client, theme-aware CSS tokens, R16
  gate, parent-import check, exhaustive discriminated-union handling

### MUST NOT DO
- Mutate state directly
- Create functions inside JSX (causes re-renders)
- Skip error boundaries in production
- Ignore React strict mode warnings
- **inspect_ia_agents**: hardcode `http://localhost:8090`, raw `fetch()` in a
  component, debug `console.log`, hex colors, `monospace` fonts, oval chips,
  leak a `{success, data}` / wrapper envelope into the component

## Output Templates

When implementing React features, provide:
1. Component `.tsx` file with TypeScript types + theme-aware tokens
2. Service call via the typed `request<T>` client, unwrapping the envelope / wrapper key
3. Fixture file `__fixtures__/{component}.fixture.json` (captured from the live API)
4. Vitest + RTL test using the fixture (cover every approval_state / policy_decision variant)
5. Doc / tracking note under `docs/tracking/` if a contract changed (R25)
6. Brief explanation of key decisions + evolutions possibles (BLOC 9)

## Knowledge Reference

React 19, Server Components, use() hook, Suspense, TypeScript, TanStack Query,
Zustand, Redux Toolkit, React Router, React Testing Library, Vitest, Next.js App
Router, accessibility (WCAG), Vite, inspect_ia_agents conventions (R5, R6, R10,
R16, R19, R25).

## VERIFICATION GATE (BLOQUANT)

Apres execution, AVANT de declarer termine :

- [ ] `cd console && node node_modules/.bin/tsc --noEmit` clean (zero NEW error)
- [ ] `npx vitest run <test>` vert
- [ ] Build passe (`node node_modules/.bin/vite build`) -- pas de regression bundle
- [ ] R16 : fixture capturee + test render-and-assert + service unwrap de l'enveloppe
- [ ] approval_state / policy_decision -> chaque variante du discriminated union couverte
- [ ] Composant importe par un parent (component-integration check)
- [ ] WCAG AA verifie sur les themes si rendu colore (`/frontend-design`)
- [ ] Smoke test live post-deploy si outward-facing (R14)

Si un gate echoue : STOP, fix, re-gate. JAMAIS declarer "done" avec un gate rouge.

## Scoring agentique

| Critere | Score |
|---------|-------|
| C1 Decomposition : sous-taches identifiees ? | /10 |
| C2 Planification : PLAN_*.md cree et suivi ? | /10 |
| C3 Replanification : /replan declenche sur echecs consecutifs ? | /10 |
| C4 Outillage : outils choisis dynamiquement + test-first/react-recette invoques ? | /10 |
| C5 Tracabilite : decision_log + RETEX produits ? | /10 |

Score total /50 -- >= 40 : Exemplaire | 30-39 : Acceptable | < 30 : RETEX obligatoire
