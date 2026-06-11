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

## 1. Coverage matrix (current truth)

Legend: DONE / PARTIAL / TODO.

### Discovery recette (corpus/repos -> SourceScanAdapter -> discovery scorecard)

| Surface | GitHub | GitLab | OpenAPI | Temporal | Manifest/MCP |
|---------|--------|--------|---------|----------|--------------|
| corpus subjects | DONE (4) | TODO | TODO | TODO | TODO |
| reference oracle | DONE | TODO | TODO | TODO | TODO |
| ground-truth schema | DONE | reuse | TODO | TODO | TODO |
| http adapter wiring | PARTIAL (assumed routes) | -- | -- | -- | -- |
| publisher | DONE (GitHub) | TODO | n/a | n/a | n/a |

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
| Ed25519 bundle contract recette | TODO |
| CI pipeline (gates + recette on push) | TODO |
| Real API wiring confirmed with colleague | TODO (blocked on his routes) |

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

### M3 -- Temporal surface  [TODO]
- `corpus/temporal/<slug>/` workflow/activity definitions (Python or pseudo-IR) that
  act as agents; ground-truth on detected workflows + action patterns + risk.
- Oracle parses workflow/activity signatures -> action patterns.
- Adapter + harness + scorecard + tests.
DoD: `recette discovery --surface temporal` -> VERDICT PASS.

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

## 4. Open decisions (need a call before/at the relevant milestone)

1. **Surface order** -- recommended M1 (Manifest/MCP) -> M2 (OpenAPI) -> M3 (Temporal),
   easiest-to-hardest. Confirm or reorder.
2. **Ed25519 bundle (M5)** -- in scope for this repo, or deferred to a Control-Plane
   recette? Earlier it was "out of scope"; the master view includes it -- confirm.
3. **Temporal corpus form (M3)** -- real Temporal SDK definitions (heavy dep) vs a
   deterministic IR the oracle parses (lighter, lab-friendly). Recommend the IR.
4. **GitLab discovery (M4)** -- needed now, or after the 4 surfaces are covered on GitHub?

---

## 5. Recommended execution order

```
M0 (done) -> M1 Manifest/MCP -> M2 OpenAPI -> M3 Temporal -> M8 orthogonality audit
          -> M4 GitLab parity -> M5 Ed25519 bundle -> M9 aggregate report
          -> M6 real wiring (whenever colleague unblocks) -> M7 CI
```

Each milestone is one writing-plans/executing-plans cycle: schema -> corpus ->
oracle -> harness -> scorecard -> tests -> gates green -> commit.
