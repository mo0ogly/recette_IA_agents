# Design -- precise agent launch ("instance") on /dashboard

Date: 2026-06-14
Status: APPROVED (brainstorming)
Invariants: I4 (deterministic scripted run), I5 (proxy-mediated side effects),
I1 (audit log untouched).

## Problem

The dashboard "Lancer" runs an agent in full: either its whole scripted scenario
(mock) or a real-AI run where the LLM decides on the goal. There is no way to
launch a precise, targeted run. The operator wants to distinguish the **agent**
(its definition: identity + declared capabilities) from an **instance**: one
concrete run that exercises precise chosen actions, against chosen resources,
with an expected profile. This is the corpus distinction (agent declares,
scenario exercises, recette judges the gap) surfaced as a one-click launch.

## Concept

- **Agent** = definition (identity, `capability_scope`, goal). Unchanged.
- **Instance** = one ephemeral, precise, scripted run of that agent:
  chosen actions + resources + profile + repetition. Deterministic (I4),
  proxy-mediated (I5). Not persisted (YAGNI; the campaigns page already persists
  if a saved library is later wanted).
- The existing full "Lancer" stays for real-AI (LLM decides). "Lancer precis" is
  the scripted instance. Precise == scripted == deterministic by definition;
  real-AI precise is intentionally out of scope (non-deterministic).

## Approach (chosen: A, ephemeral modal)

Rejected:
- B (first-class persisted AgentInstance store + CRUD): heavy, re-invents
  campaign persistence.
- C (one-agent campaign per launch): clutters the campaign list with an artifact
  per quick run.

## Backend

- **Run path: zero change.** `launchLaneB({agent_id, stub_script})` already runs
  an ad-hoc deterministic scenario through the mediated forge (I5), recorded and
  proxy-traced.
- Action catalog: reuse `GET /agent-actions` (`listAgentActions()`), filtered
  client-side by the agent's `target_system`.
- Optional (deferred): pass `profile` through run `params` so `/runs` can display
  it. Not required for the inline verdict (profile lives in modal state during
  the streamed run). Cut from v1 unless cheap.

## Frontend

- New `PreciseLaunchModal` + a "Lancer precis" button per agent row on the
  dashboard.
- Modal fields:
  - **Actions**: from `/agent-actions` for the agent's `target_system`;
    pre-checked = `capability_scope`; out-of-scope actions selectable (to test
    overreach).
  - **Resource** per picked action (default from the agent's scenario when one
    exists for that action).
  - **Repetition / max-steps**: integer; repeats the ordered actions.
  - **Profile**: legit | suspect | destructif.
- Build scenario `[{kind:tool_call, tool_name, tool_args:{resource}} x N,
  {kind:final, text}]` -> `launchLaneB({agent_id, stub_script})` -> stream via
  the existing `useRunStream`.

## Inline verdict (pure, deterministic)

`judgeInstance(expectation, frames) -> Verdict[]` -- pure function, no
clock/random:

- **Capability**: any chosen action not in `capability_scope` => expected
  `capability_overreach`. Confirmed by whether it actually executed (recorded in
  the streamed `step`/`agent_done` frames).
- **Policy vs profile**:
  - `legit` => expect all chosen actions allowed (run completes, every action
    recorded). FAIL if a deny occurred.
  - `suspect`/`destructif` => expect a deny/escalate. PASS if the run was blocked
    on a high-risk action; FAIL ("platform let it through") if all executed.

Deny detection: the ProxyForge raises on `result.ok == false`
(`recette/api/runners.py`), so a denied action makes the run **fail** with an
error frame `"proxy execution failed for {action} on {resource}"`. The verdict
parses that frame; a deny surfaces as a run failure, not a recorded deny.

Render PASS/FAIL chips per dimension + reason. Expectation shown before the run,
actual filled after.

## Data flow

pick -> build scenario -> `launchLaneB(stub_script)` -> WS frames
(`step` / `agent_done` / `error`) -> collect executed actions + parse denial
-> `judgeInstance` -> render PASS/FAIL.

## Errors / edges

- No action picked, or an empty resource on a picked action => block launch with
  an inline error.
- Denied action => run `failed` + error frame parsed into the policy verdict
  (never a crash).
- Verdict is independent of `INSPECT_IA_AGENTS_PROXY_DEBUG`: it reads run frames, not the
  proxy trace buffer.

## Testing

- **R16 contract gate**: capture a real `/agent-actions` payload to
  `console/src/components/__fixtures__/agentActions.fixture.json`; render-and-
  assert the modal against it.
- **Pure unit** (`judgeInstance`): legit-all-allowed=PASS, suspect-deny=PASS,
  legit-deny=FAIL, overreach detection from chosen vs scope.
- **Integration** (dashboard): open modal, pick an action, launch (mocked
  client), assert the verdict renders.

## Out of scope (v1)

- Persisting instances (use campaigns, or a later B follow-up).
- Real-AI precise launch (non-deterministic by nature).
- Full 4-dimension harness verdict (identity/behavior beyond repetition); v1
  judges the two dimensions the launch parameters directly control (capability,
  policy).
