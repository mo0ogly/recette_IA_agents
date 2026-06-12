# MASTER PLAN -- AgentRail Recette Platform

> Single source of truth for the recette platform roadmap. Every milestone has a
> status, a scope, the files it touches, and a Definition of Done. Update the status
> column as work lands. This file exists so steps stop being forgotten.

**Date:** 2026-06-11
**Maintainer:** fabricepizzi@gmail.com
**Scope:** Build the corpus + validation harness that proves the colleague's tools work.
We build the test subjects + the oracle + the scorecards. We do NOT build the tools
under test (Discovery/Enrichment Plane, Identification, Risk Engine, Railgun gateway).

---

## 0. What we validate (the two tools, the four surfaces)

The colleague's Discovery/Enrichment Plane has **four scanner surfaces**:

| Surface | What the scanner reads | AgentActionEvent target |
|---------|------------------------|-------------------------|
| GitHub | agent code + CI/CD in a repo | `target_system = github` |
| OpenAPI | an OpenAPI/Swagger spec exposing agent endpoints | `target_system = openapi` |
| Temporal | Temporal workflows/activities acting as agents | `target_system = temporal` |
| Manifest/MCP | an AgentRail JSON manifest / MCP server descriptor (highest precision) | `target_system = mcp` |

Two tools consume the corpus:

- **Discovery** -- must DETECT each agent surface and emit `discovery_risks`
  (opaque `canonical_agent_id`, `action_pattern`, `target_system`, `estimated_risk`,
  `generated_policy`). Scored on invariant properties, never opaque values.
- **Identification** -- must JUDGE each agent on the 4 dimensions (identity,
  capabilities declared-vs-real, policy conformance, behavior) + global verdict.

Plus a downstream contract: Risk Scoring Engine -> **Ed25519-signed policy bundle**
-> Railgun. The recette must be able to assert the bundle is well-formed and signed.

---

## 0bis. Agent execution model -- HYBRID, two lanes (resolved 2026-06-11)

The structural decision that shapes the whole platform and Track U:

- **Lane A -- Ground-truth corpus (the measurable recette).** Deterministic subjects
  (action-logs, repo trees, OpenAPI specs, Temporal workflows). I4/I7-safe: a re-run is
  byte-identical. This is the ONLY lane scored against ground-truth. ALL existing work
  (M0) and every surface milestone (M1-M9) live here.
- **Lane B -- Live LLM agents (realism/demo in the console).** Agents driven by real AIs
  for the "most-real-possible" experience. Inherently non-deterministic, so **every run is
  RECORDED** (prompt / response / actions -> event log) to stay replayable after the fact.
  Lane B output is NEVER used as ground-truth; it powers the console's launch / monitor /
  debug experience only.

Consequence: Track U's "configure AIs" + "launch/stop agents live" are Lane B; the
scorecards and surface milestones stay Lane A. The two lanes share the canonical
`AgentActionEvent` shape and the forge abstraction, never the ground-truth role.

---

## 1. Coverage matrix (current truth)

Legend: DONE / PARTIAL / TODO.

### Discovery recette (corpus/repos -> SourceScanAdapter -> discovery scorecard)

| Surface | GitHub | GitLab | OpenAPI | Temporal | Manifest/MCP |
|---------|--------|--------|---------|----------|--------------|
| corpus subjects | DONE (4) | DONE (4) | DONE (4) | DONE (4) | DONE (4) |
| reference oracle | DONE | DONE (manifest) | DONE (json) | DONE (AST) | DONE (manifest) |
| ground-truth schema | DONE | DONE (reuse) | DONE (reuse) | DONE (reuse) | DONE (reuse) |
| http adapter wiring | PARTIAL (assumed routes) | DONE (same oracle/mock) | DONE (same oracle/mock) | DONE (same oracle/mock) | DONE (same oracle/mock) |
| publisher | DONE (GitHub) | TODO (deferred) | n/a | n/a | n/a |

### Identification recette (corpus/agents -> IdentificationAdapter -> 4-dim scorecard)

| Axis | GitHub | GitLab |
|------|--------|--------|
| correct subjects | DONE (1) | DONE (1) |
| incorrect (4 violation types) | DONE (4) | DONE (4) |
| reference oracle (4 dims) | DONE | DONE |
| http adapter (real tool) | TODO | TODO |

### Cross-cutting

| Item | Status |
|------|--------|
| Docker lab (runtime/audit, non-root) | DONE |
| One-shot installer + smoke tests | DONE |
| Strict gates (ruff/mypy/bandit) green | DONE |
| Ed25519 bundle contract recette | DONE (M5) -- recette bundle-verify + fixtures |
| CI pipeline (gates + recette on push) | DONE (M7) -- .github/workflows/recette.yml, green on main |
| Aggregate report (`recette report`) | DONE (M9) |
| Real API wiring confirmed with colleague | TODO (blocked on his routes) |
| Lane B agent engine (live LLM, record/replay/promote, real-mode guard) | DONE (LB1-LB7) -- recette agent run/replay/freeze |
| UX control console (launch/stop/monitor + Monaco + config) | TODO (Track U: U1 FastAPI API -> U2-U4 React/Monaco) |

---

## 2. Milestones (ordered, each independently shippable)

### M0 -- Foundations  [DONE]
Docker multi-stage lab, installer, gates, GitHub discovery + identification corpus.
DoD: `make install` green end-to-end. **Met.**

### M1 -- Manifest/MCP surface  [TODO]  (recommended next)
Highest-precision scanner, smallest corpus, validates the abstraction generalizes
beyond GitHub before tackling harder surfaces.
- Add `target_system = mcp` to the action/target vocabulary (`recette/events.py`).
- `corpus/manifests/<slug>/` subjects: an `.agentrail` manifest + MCP descriptor,
  with `discovery-ground-truth.json` (detection, action coverage, risk rank, policy).
  Set: 1 read-only, 1 bounded-write, 1 overreach, 1 true-negative.
- Extend `ReferenceSourceScanAdapter` to parse a manifest/MCP surface (manifest-first).
- Harness: make `discover_repo_dirs` surface-agnostic (glob ground-truth across
  `corpus/{repos,manifests}/`), or add a `--surface` selector.
- Tests: schema, corpus consistency, reference scan determinism, scorecard.
DoD: `recette discovery --adapter reference --surface mcp` -> VERDICT PASS; gates green.

### M2 -- OpenAPI surface  [TODO]
- `corpus/openapi/<slug>/spec.yaml` realistic OpenAPI specs exposing agent endpoints
  (read-only reporter, write-capable bot, overreach, non-agent API as true negative).
- Oracle parses paths/verbs -> action_pattern (GET=read, POST/PUT/DELETE=write/escalate),
  risk rank from verb set + auth scheme.
- ground-truth schema variant or reuse with `target_system = openapi`.
- Adapter + harness + scorecard + tests.
DoD: `recette discovery --surface openapi` -> VERDICT PASS.

### M3 -- Temporal surface  [DONE 2026-06-11]  (FIRST of the remaining surfaces, per decision #1)
Shipped: 4 real temporalio subjects + AST oracle + `--surface temporal` + 8 tests; gates
green; docker http github+temporal VERDICT PASS. Deviation: the `temporal-dev` compose
service is DEFERRED to Lane B (discovery uses static AST analysis, needs no running server).
Real Temporal SDK definitions (decision #3). Heavier than the other surfaces, done first.
- `[temporal]` optional extra (`temporalio` SDK); `temporal-dev` service in docker-compose
  (Temporal dev server) so the lab can run real workflows; lab stays the default and
  needs none of this unless the Temporal surface is exercised.
- `corpus/temporal/<slug>/` real workflow/activity definitions acting as agents
  (read-only reporter, write-capable, overreach, non-agent). ground-truth on detected
  workflows + action patterns + risk rank + policy.
- Determinism (I4): capture workflow time/history; assert re-run yields identical events.
- Oracle parses workflow/activity signatures -> action patterns; adapter + harness +
  scorecard + tests; surface-agnostic `--surface temporal`.
DoD: `recette discovery --surface temporal` -> VERDICT PASS; gates green; re-run deterministic.

### M4 -- GitLab discovery parity  [TODO]
- Mirror the 4 GitHub discovery repos for GitLab (`gl-*`), CI = `.gitlab-ci.yml`.
- Publisher: add a GitLab backend (python-gitlab, `[real]` extra), dry-run default.
DoD: discovery corpus covers github + gitlab; publisher dry-run tested for both.

### M5 -- Ed25519 signed-bundle contract recette  [TODO]
- Schema for the policy bundle (decision set + policy version + signature).
- `recette bundle-verify <bundle>`: validate shape + verify Ed25519 signature against
  a published public key (key via env, never hardcoded -- R8).
- Fixture bundle (valid) + negative fixtures (tampered payload, wrong key, missing sig).
- Tests assert accept-valid / reject-each-tampering.
DoD: `recette bundle-verify` passes valid, rejects all negatives.

### M6 -- Real API wiring (unblock when colleague confirms routes)  [TODO, BLOCKED]
- Confirm `:8081` REST routes + `estimated_risk` JSON shape; adjust
  `recette/http_adapter.py` constants. Add real-tenant smoke in the runbook.
- Identification: implement the real `IdentificationAdapter` over the colleague's API.
DoD: `recette discovery --adapter http` + identification http run green vs the real service.

### M7 -- CI pipeline  [TODO]
- GitHub Actions workflow: on push/PR -> `make docker-gates` + `make docker-test` +
  `recette discovery --adapter reference` (all surfaces) + `recette run`.
- Badge in README. Pin tool versions in the audit stage for reproducibility.
DoD: CI green on a PR; red on an injected corpus/oracle mismatch.

### M8 -- Negative-corpus depth + orthogonality audit  [TODO]
- For every surface, ensure >= 1 correct and >= 1 incorrect per violation_type, each
  breaking exactly one dimension (existing `test_each_negative_breaks_exactly_one_dimension`
  generalized to all surfaces).
DoD: orthogonality test passes across all surfaces; coverage report printed.

### M9 -- Aggregate scorecard + report  [TODO]
- `recette report`: run identification + discovery (all surfaces), emit one aggregate
  (detection rate, per-dimension accuracy, FP/FN, per-surface breakdown), JSON + text.
DoD: single command produces the full recette verdict for a release gate.

---

## 3. Cross-cutting workstreams (run alongside milestones)

- **Determinism (I4/I7):** every new oracle/adapter is deterministic (LogicalClock,
  no wall-clock/random); add a re-scan determinism assertion per surface.
- **No opaque-value comparison:** ground-truth asserts invariant properties only.
- **Secrets:** real tokens/keys via env only; `.env.example` documents the variables.
- **Docs:** one runbook section per surface; keep this MASTER plan's status current.
- **Traceability:** log architecture choices in `docs/tracking/decision_log.jsonl`.

---

## 4. Decisions (resolved 2026-06-11)

1. **Surface order** -- RESOLVED: **Temporal first**, then OpenAPI, then Manifest/MCP.
   (Business priority over easiest-first; accepts the added Temporal infra cost below.)
2. **Ed25519 bundle (M5)** -- RESOLVED: **in scope** for this recette.
3. **Temporal corpus form (M3)** -- RESOLVED: **real Temporal SDK** definitions, not an IR.
   Implications: needs a Temporal dev server in the lab (docker-compose service) and a
   `[temporal]` optional extra; non-determinism (workflow time/random) MUST be captured
   so replay stays deterministic (I4) -- use Temporal's deterministic time + recorded
   history, assert re-run yields identical event sets.
4. **GitLab discovery (M4)** -- after the surfaces are covered (kept at M4).
5. **UX console (Track U)** -- NEW requirement: a console to launch/stop/integrate/monitor
   agents, a Monaco debug view, and a config area for agents + AIs. See Track U (section 6).
6. **Agent execution model** -- RESOLVED: **hybrid, two lanes** (see 0bis below).
   Lane A = deterministic ground-truth corpus (the measurable recette, I4-safe).
   Lane B = live LLM-powered agents for realism/demo in the console, every run RECORDED,
   NEVER used as ground-truth.
7. **API backend** -- RESOLVED: **FastAPI (Python)**, reuses the recette package directly.

---

## 5. Execution order (resolved)

We STARTED with GitHub -- it is the established base (M0 done: GitHub discovery +
identification). The remaining surfaces follow the resolved order Temporal -> OpenAPI ->
Manifest/MCP.

```
M0 GitHub                         DONE
  -> M3 Temporal (real SDK)         DONE 2026-06-11
  -> M2 OpenAPI                     DONE 2026-06-11
  -> M1 Manifest/MCP                DONE 2026-06-11
  -> M9 aggregate report            DONE 2026-06-11 (brought forward)
  -> M7 CI                          DONE 2026-06-11 (green on main)
  -> M5 Ed25519 bundle contract     DONE 2026-06-11 (brought forward)
  -> M8 orthogonality + coverage audit       DONE 2026-06-11
  -> M4 GitLab parity               DONE 2026-06-11 (publisher backend deferred)
  -> M6 real API wiring (when colleague unblocks)   <- blocked
  -> Track U UX console             <- the remaining large effort

Track U (UX console) runs in parallel once M3 lands -- it needs at least one
non-GitHub surface to be worth wiring, and an API layer (U1) it can drive.
```

Each milestone is one writing-plans/executing-plans cycle: schema -> corpus ->
oracle -> harness -> scorecard -> tests -> gates green -> commit.

---

## 6. Track U -- UX control console (NEW)

Goal: a console to launch/stop/integrate/monitor the test agents, a Monaco-based
debug view of what each agent does, and a configuration area for agents + AIs.
This sits ON TOP of the existing recette (it drives the same corpus + harness + forge),
it does not replace the CLI.

### U1 -- Recette API layer  [DONE 2026-06-12]  (prerequisite for the UI)
Shipped: FastAPI app (recette/api/) — /health, config CRUD, catalog, runs (launch/inspect/stop/events), WebSocket live stream, Lane B run wiring (stub+live), /agents/register; transport = WebSocket; secrets via env (R8); lab default. 8 api test modules; gates green.
- A backend API (FastAPI, Python -- matches the recette package) exposing:
  list/register agents (corpus), launch a run (replay a scenario against lab or real
  forge), stop a run, stream events (SSE/WebSocket), fetch logs + scorecards, config CRUD.
- Reuses `recette/*` directly; no business logic duplicated in the API.
- Secrets (tokens, AI keys) via env only (R8); lab mode is the default.
DoD: every CLI capability reachable over the API; a launched run streams events.

### U2 -- Console frontend  [TODO]
- React + TypeScript + Vite (AgentRail console stack). Views: agent catalog,
  launch/stop controls, run status, live event feed, scorecard rendering.
- R16 frontend contract gate: real fixture payloads + render-and-assert per component.
DoD: launch an agent from the UI, see it run and its scorecard, stop it.

### U3 -- Monaco debug console  [TODO]
- Embedded Monaco editor: view the agent's scenario/code and a live, correlated
  event/log stream (by event_id/agent_id) to debug what an agent is doing.
- Read-only first; editing scenarios from Monaco is a later enhancement.
DoD: select a running agent -> Monaco shows its definition + live event trace.

### U4 -- Configuration area (agents + AIs)  [TODO]
- Configure agents (identity, capability_scope, runtime lab/real) and AI backends
  (provider, model) used by any LLM-powered agents. Keys via env/secret store only.
- Persisted config in a single versioned source (R5), never hardcoded.
DoD: create/edit an agent + an AI backend from the UI; config round-trips and validates.

### Track U decisions (resolved 2026-06-11)
- **Agent execution model** -- RESOLVED: **hybrid two-lane** (section 0bis). Lane A drives
  the scorecards (deterministic); Lane B drives live LLM agents in the console (recorded).
- **API backend** -- RESOLVED: **FastAPI (Python)**, reuses the recette package directly.
- **Real-time transport** -- RESOLVED 2026-06-12: WebSocket (see docs/tracking/decision_log.jsonl).
- **Scope/timing** -- RESOLVED: start Track U after M3 (one real non-GitHub surface exists)
  and once U1 (the FastAPI layer) is in place.
