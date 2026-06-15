# Design -- Per-agent / per-server action pacing (temporization)

Date: 2026-06-15
Status: APPROVED (brainstorming) -- next: writing-plans

## Problem

Lane B agents chain their actions as fast as the LLM + forge allow. The
operator wants to insert a configurable **delay between an agent's actions** so
a too-fast agent can be slowed for observation in the cockpit ("lux" = the
flux/live/cockpit views). The delay must be settable **per agent OR per server**
and editable **via the cockpit UX**, not only by hand-editing JSON.

## Invariant constraint (the crux)

I4 / R20 forbid `time`/`sleep`/`random` in the agent execution, decision, or
judge path. A pacing delay is **operational metadata**, never a decision input
-- exactly the "ops metadata vs decision data" boundary from
`.claude/rules/maf-standard.md` (like `Run.created_at`). The judged output
(`AgentAction` log + `Recording`) MUST stay byte-identical whatever the pace.

## Architecture & I4 boundary (Section 1)

```
config (server.pace_ms / agent.pace_ms)
        |
        v  resolve: agent ?? server ?? 0
runners.py  on_step wrapper  --> time.sleep(pace, sliced, checks should_stop)
        |                          ^ the ONLY place that sleeps
        v
lane_b.run_agent  (PURE, no `time` import)  --> AgentAction log byte-identical
        |
        v
emit("step") --> SSE spaced --> cockpit paced for free
```

- `lane_b.py`, `harness`, judge, replay (`ReplayLlm`): zero sleep -> I4/R20
  intact, gates green, tests fast.
- The sleep lives in the worker thread (`recette/api/runs.py::_execute`), so it
  never blocks the async API event loop.
- Spacing the server-side `emit("step")` calls naturally spaces the SSE frames,
  so the cockpit is paced with no separate client buffering logic (YAGNI).

## Config, resolution, schema (Section 2)

- Optional `pace_ms: integer >= 0` added to the agent entry AND the server entry
  in `config/inspect_ia_agents.config.json`. Absent / 0 = current behaviour
  (instant). Full backward compatibility.
- Resolution helper (pure, testable) in `recette/api/runners.py`:
  `resolve_pace(agent_cfg, server_cfg) -> agent.pace_ms if set else
  server.pace_ms if set else 0`. `server_cfg` is matched from
  `config_store.list_servers()` on `agent_cfg["server"]` (already resolved for
  the forge).
- Safety clamp `[0, MAX_PACE_MS]` (e.g. 30000) via a single config constant
  (R5), not a scattered literal, so a run can never be frozen.
- Agent schema gains the optional field with `>= 0` integer validation.

## UI cockpit -- R16 contract gate (Section 3)

- Agent editor (`console/src/pages/agents/index.tsx`) and the server editor get
  a numeric **"Cadence (ms)"** field; empty = inherit / instant. Saved through
  the existing `PUT /config/agents|servers/{id}` patch route (`{pace_ms}`).
- Cockpit shows a "pace 800ms" badge on an agent when pacing is active
  (legibility-first).
- R16: real captured payload in `__fixtures__/*.fixture.json` including
  `pace_ms`, a render-and-assert test, service unwraps the `{success,data}`
  envelope. "The type compiles" is not the contract.

## Error / stop during sleep (Section 4)

- Sleep is **sliced** (e.g. 100 ms ticks) inside a loop that checks
  `should_stop()` -> operator stop stays responsive even mid-delay, never a
  blocked 30 s wait.
- Pace is pure ops: a resolution error (server not found) falls back to pace 0
  (fail-safe to instant, never crashes the run), consistent with
  `.claude/rules/failure-modes.md`.
- Never on the decision path -> zero impact on verdict / replay.

## Tests + gates (Section 5)

- Unit `resolve_pace`: agent override, server inheritance, default 0, clamp.
- Replay / I4: assert the `AgentAction` log + `Recording` are byte-identical for
  `pace_ms=0` vs `pace_ms=500` (pace does not touch the judged output);
  `time.sleep` monkeypatched to a no-op so the test stays fast.
- Stop-during-sleep: `should_stop` true -> the slice loop exits quickly.
- R16 console: render + fixture.
- Gate before done: `make gates`, `./recette.sh test`, `make recette`
  (coverage guard), `./recette.sh console-test`, `./recette.sh console-build`,
  smoke if a live proof is needed.
- `lane_b.py` keeps no `time` import -> a guard grep can enforce it.

## Out of scope (YAGNI)

- Jittered / random delay ranges (fixed delay chosen).
- Named pace profiles.
- Client-side playback buffering (server SSE spacing covers the cockpit).
