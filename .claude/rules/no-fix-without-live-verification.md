# R26 No Fix Without Live Verification

## Why this rule exists

Incident 2026-04-24 (Launch Survey Compliance Frameworks): I declared
"prod reparee, testez" after redeploying the frontend bundle. The bundle
was indeed served 200 and the login screen rendered -- so I concluded
"done". The user tested and the real bug was still there: clicking
Launch Survey created an assessment but did NOT navigate to the detail
page (sessionStorage vs localStorage mismatch in the `onCreated` callback).

I shipped "fixed" without verifying the actual user flow demanded by the
user. The user had to reverify himself, catch the bug, and feed me back
the logs to identify the real root cause.

This rule extends R17 (which only covers new components with API calls)
to ANY change I declare "fixed", "resolved", "deployed", or "ready to test".

## The rule (BLOCKING for any "fix done" claim)

Before writing any phrase that claims success, completion, or readiness
of a fix -- such as "reparee", "fix deploye", "resolu", "corrige",
"fonctionne maintenant", "pret a tester", "testez maintenant",
"deploy OK", "production repaired" -- I MUST have ALL THREE pieces:

1. **User-flow executed step-by-step**, not just a surface-level check.
   - Web UI change -> Playwright MCP navigates the actual flow the user
     asked about (not just page load).
   - Backend API change -> curl/Playwright fetch of the actual endpoint
     with expected payload, check response shape AND status.
   - Infra/deploy change -> end-to-end request through nginx + backend +
     PostgreSQL (not just `systemctl is-active`).

2. **Assertion visible in logs/DOM that proves expected behavior occurred.**
   Not just "returns 200". Must match the semantics of the user request.
   Example: user reports "Launch Survey does not navigate" -> proof is
   `[APP] Storage-driven navigation {from: frameworks-manager, to:
   smsi-assessment-detail}` in console logs AFTER the click, not just
   "dialog opens".

3. **Screenshot or snapshot ARIA** (or equivalent log capture for CLI
   flows) showing the final state. If the flow produced a navigation,
   snapshot the destination page. If it produced a created entity,
   snapshot the entity visible in the UI.

## Escape hatches (allowed, but MUST be explicit)

When verification is impossible or out of scope, I MUST say ONE of
these EXACT phrases before claiming delivery:

- **"fix deploye, non verifie"** + the exact reason (e.g. "pas d'acces
  login utilisateur", "require production data", "flow necessite
  authentification 2FA")
- **"livre, a verifier par toi"** + the exact steps the user must run
- **"fix appliquer, test manuel requis"** + what to check

Then I hand verification explicitly to the user. No weasel wording
("ca devrait marcher", "normalement ok", "je pense que ca va").

## Forbidden patterns

- Any claim of success after a BUILD passes but before a user-flow runs
- "Bundle deployed 200" as proof that the feature works (it only proves
  the bundle is served -- see R18 No Deduction)
- "TypeScript compiles" as proof the logic is correct
- "Service is active" as proof the request succeeds end-to-end
- "I fixed the handler" before running the handler from the UI
- Starting any post-fix sentence with "Mea culpa", "Tu as raison",
  "Desole", "Je m'excuse". If I owe a correction, just deliver the
  root cause + fix + proof. The user's time is not consumed by
  apology preambles.

## Scope

This rule applies to ALL changes declared "fixed":
- Frontend React / TypeScript
- Backend Rust / Python handlers, services, middleware
- Infra : deploy.sh runs, systemctl restarts, nginx config reloads,
  PostgreSQL migrations applied
- Recette corpus / ground-truth manifests committed
- Any skill output presented to the user as "ready"

## Enforcement

### Layer 1 -- This rule file (convention + loaded in every prompt)

Referenced in `.claude/CLAUDE.md` so it is in context for every turn.

### Layer 2 -- Skill `/verify-fix` (tool-provided workflow)

Invoke BEFORE claiming a frontend/UI fix is done. It scripts the
Playwright flow + log capture + screenshot in a single pass. See
`.claude/skills/verify-fix/SKILL.md`.

### Layer 3 -- Hook `no_fix_without_live_verify.sh` (technical gate)

Stop hook that scans my response for success-claim patterns and blocks
the Stop if none of these are true:

- Response contains one of the explicit escape phrases above
- A recent `.claude/state/playwright_recent` marker exists (mtime
  within 15 minutes), created by a companion `PostToolUse` hook that
  listens for `mcp__playwright__browser_*` tool calls
- `.claude/state/verify_ack` exists and is newer than the last claim

Exit 2 from the hook blocks the Stop and prints the missing proof.

## Related rules

- R17 Frontend Contract Gate -- similar philosophy but narrower (only
  new components with API calls). R26 generalizes to any change.
- R18 No Deduction -- "the binary serves 200 = the feature works" is
  deduction. R26 is the applied version for user-facing changes.
- R24 No Backslash Copy-Paste -- similar focus on the user experience
  (don't ship a broken line break, don't ship an unverified fix).
- Anti-rationalization hook (`anti_rationalization.sh`) -- catches
  "I think it should work". R26 hook is the mirror: catches "it works"
  without proof.
