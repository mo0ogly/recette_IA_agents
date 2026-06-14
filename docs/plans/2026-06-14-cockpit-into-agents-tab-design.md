# Design -- Cockpit as an Agents sub-tab + fix the broken mock run

Date: 2026-06-14
Status: IMPLEMENTED
Plane: console (frontend), no invariant change. Mock runs still go through the
lab proxy (I5); determinism (I4) unchanged.

## Problem

Two issues reported on `http://localhost:5173/cockpit`:

1. **Wrong place.** The Cockpit nav entry sat at position 2 (right after the
   dashboard), far from Agents. The operator wants it as a detailed
   creation/debug tool living *inside* the Agents page.
2. **"Marche pas".** Launching a mock run failed with
   `proxy execution failed for read_repo on 'acme/x': lab returned HTTP 404`.
   Root cause: the cockpit auto-selected the first agent (`camp-rogue-bot`,
   `target_system=okta`) but the default mock script was hardcoded to a github
   action `read_repo`. The okta lab domain does not handle `read_repo`, so the
   proxy returned 404 and the run failed before doing anything.

## Decision

- **Cockpit becomes a sub-tab of the Agents page.** The page gains a tab bar:
  `Configuration` (the existing agent CRUD table + create/edit form + run log)
  and `Cockpit -- lancer & debug` (the existing `CockpitPage`, mounted as-is).
  The top-level `Cockpit` nav entry is removed; the `/cockpit` route now
  redirects to `/agents` so old links/bookmarks still resolve.
- **The default mock script is derived from the selected agent**, not
  hardcoded. `defaultStubScriptFor(agent)` scripts the agent's first declared
  `capability_scope` action (always handled by its own target domain). An agent
  with an empty scope (a probe) gets a `final`-only script: no tool call, so it
  cannot 404. Switching agent in the picker re-derives the script; the operator
  can still edit it.

## Why this approach

- Reuses `CockpitPage` verbatim -> its unit tests stay valid, minimal surface.
- The 404 fix is structural (the script follows the agent's real capabilities)
  rather than swapping one hardcoded action for another.
- Redirect over delete avoids dead links for one line of cost.

## Verification (live, R14)

A/B at the run level against the live API (okta agent `camp-identity-admin`):

| Script | Result |
|--------|--------|
| old hardcoded `read_repo` | `status=failed`, `error=...read_repo...HTTP 404` |
| derived `suspend_user` (scope[0]) | `status=completed`, `error=None` |
| empty-scope probe `camp-rogue-bot` (final only) | `status=completed`, `error=None` |

`console-build` (tsc strict + vite) green; agents + cockpit vitest suites green.

## Files

- `console/src/pages/cockpit/index.tsx` -- `defaultStubScriptFor` + re-derive on
  agent switch.
- `console/src/pages/agents/index.tsx` -- tab state + tab bar + embed CockpitPage.
- `console/src/pages/agents/agents.css` -- underline tab styles.
- `console/src/App.tsx` -- drop Cockpit nav link, redirect `/cockpit` -> `/agents`.
