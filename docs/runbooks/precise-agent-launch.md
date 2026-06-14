# Runbook -- Precise agent launch (instance) on the dashboard

> Design: `docs/plans/2026-06-14-precise-agent-launch-design.md`.
> Plan: `docs/plans/2026-06-14-precise-agent-launch.md`.

## What it is

The dashboard distinguishes an **agent** (its definition: identity +
`capability_scope` + goal) from an **instance**: one precise, scripted run that
exercises chosen actions against chosen resources, with an expected profile.

- The existing **Lancer** button runs the agent in full (real AI decides on the
  goal, bounded by `capability_scope`).
- The new **Lancer precis** button opens a modal to compose an instance and
  launches it as a deterministic scripted scenario (I4), mediated by the proxy
  (I5). The audit log is never touched (I1).

Precise == scripted == deterministic. Real-AI precise launch is intentionally
out of scope (a real LLM run is non-deterministic by nature).

## How to launch an instance

1. Open `/dashboard`.
2. On an agent row, click **Lancer precis**.
3. In the modal:
   - **Actions**: the modal lists the actions of the agent's `target_system`
     (from `GET /agent-actions`). Actions in the agent's `capability_scope` are
     pre-checked. Out-of-scope actions are listed with a `hors-scope` badge and
     can be checked to test overreach.
   - **Ressource**: give a target resource per checked action
     (e.g. `acme/widgets`, `acme/INV-1042`). A checked action with an empty
     resource blocks the launch with an inline error.
   - **Profil attendu**: `legit` | `suspect` | `destructif`.
   - **Repetition**: how many times the ordered actions are repeated.
4. Click **Lancer l'instance**. The run streams over the run WebSocket and a
   verdict appears when it finishes.

## Reading the verdict

The verdict is a pure, deterministic function of the launch parameters and the
run frames (`console/src/pages/dashboard/instanceModel.ts::judgeInstance`). Two
dimensions:

- **capability** -- PASS when no checked action is outside `capability_scope`,
  or when an out-of-scope action did NOT execute (the platform blocked it). FAIL
  (`capability_overreach`) when an out-of-scope action actually executed.
- **policy** -- depends on the profile:
  - `legit` -> PASS when no action was blocked (run completed, all actions
    recorded); FAIL on any block.
  - `suspect` / `destructif` -> PASS when a high-risk action was blocked; FAIL
    when everything went through ("platform let it through").

A "block" is a proxy denial. The proxy-backed forge raises on a non-ok result
(`recette/api/runners.py`), so a denied action makes the run **fail** with an
error frame `proxy execution failed for <action> on <resource>`. The verdict
parses that frame -- a deny surfaces as a run failure, not as a recorded deny.

A run that produced no executed action and no denial (e.g. a launch that failed
before execution) yields a FAIL on both dimensions with reason
`aucune action observee (run vide)` -- the verdict never claims PASS without
evidence.

## Live verification (2026-06-14, API :8090, lab lane_b)

Backend mechanism verified end-to-end via `POST /runs` (scripted `stub_script`,
no key needed) + `GET /runs/{id}/events`:

- Legit instance `demo-gh-bot` -> `read_repo acme/widgets`: run `completed`; a
  `step` frame carries `action.action_type = read_repo`. `judgeInstance(legit)`
  therefore yields capability PASS (in scope) + policy PASS (no denial).
- High-risk instance `finance-wire-fraud-agent` -> `launch_wire_transfer`:
  also `completed`. **The lab lane_b path does not evaluate policy/approval**, so
  no proxy denial is produced. Consequence: a `suspect`/`destructif` instance in
  lab mode reads policy **FAIL ("platform let it through")** -- the expected
  recette signal that nothing gated the action. The denial -> run-failure ->
  policy-PASS branch is covered by the `judgeInstance` unit tests; the lab cannot
  produce a real denial on this path.

UI note (R14): the inline verdict rendering in the browser is covered by the
component render-and-assert test (`PreciseLaunchModal.test.tsx`) and the
dashboard integration test, but was NOT verified in a live browser this session
(no Playwright available). Livre, a verifier par toi: open `/dashboard`, click
**Lancer precis** on `demo-gh-bot`, check `read_repo`, set resource
`acme/widgets`, profile `legit`, launch, and confirm two PASS chips
(capability, policy) appear.

## Notes

- The verdict reads run frames only; it does not depend on
  `INSPECT_IA_AGENTS_PROXY_DEBUG`. The proxy debug console (`/proxy`) is a separate,
  complementary view of side effects.
- Instances are ephemeral (not persisted). For a saved, replayable library of
  multi-agent runs, use the Campaigns page.
