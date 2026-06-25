# Behavior <-> Discovery Correlation -- design (research instrument, Approach A)

Date: 2026-06-25
Status: APPROVED (approach A, phased P1->P3). UI is a P1 deliverable, not P3.

## Problem

The AI-research team needs to USE the platform to analyze agent behavior in
relation to the discovery engine. Today the two engines never meet:

- **Discovery** reads SOURCE (`corpus/repos/<slug>`, a static publishable repo):
  what an agent DECLARES -- detection, action_pattern, target, relative risk
  order, policy presence. Ground-truth is invariant properties only, never an
  opaque score.
- **Behavioral-analysis engine** reads RUNTIME evidence (ebpf / proxy /
  action-log bundles): what an agent DID -- egress, dns, credential, doh,
  process, said-vs-done, plus a `behavioral_score`.

The corpus subjects do not even share identity: discovery slugs (`gh-pr-bot`,
`gh-supply-chain-compromise`) are distinct from runtime subjects
(`corpus/agents/`, `corpus/sim/`). The bridge is genuinely missing.

## Core idea -- discovery PREDICTS, behavior MEASURES

Discovery is a STATIC risk predictor; the behavioral engine is the RUNTIME
ground-truth. The research value is the **agreement** between them, and
especially the disagreement:

|                       | runtime clean   | runtime dirty              |
|-----------------------|-----------------|----------------------------|
| source low-risk       | agree_clean     | **STATIC_BLIND** (scanner false negative) |
| source high-risk      | static_overflag | agree_dirty                |

`STATIC_BLIND` -- a repo that looks clean to the source scanner but exfiltrates /
escalates / tunnels at runtime -- is the headline research deliverable.

## Approach A (chosen)

A thin identity map joins the two existing engines in a downstream, pure
function. Discovery and behavior stay UNCHANGED.

### New artifacts

```
corpus/agent_links.json                        # identity map: agent_id -> {discovery, runtime}
recette/behavior/correlate.py                  # pure correlate(...) -> CorrelationReport
recette/cli/behavior_cmds.py                   # + `recette analyze correlate`
recette/api/routers/behavior.py                # + POST /behavior/correlate
console/src/pages/probe/CorrelationPanel.tsx   # the Lux: steering wheel + windshield
console/src/pages/probe/__fixtures__/correlation.fixture.json
docs/runbooks/behavior-discovery-research.md   # the team runbook
tests/test_behavior_correlate.py
console/src/pages/probe/CorrelationPanel.test.tsx
```

### agent_links.json (the only new ground-truth)

Hand-maintained until P3 builds full twins. One entry per agent_id:

```json
{ "version": 1, "links": [
  { "agent_id": "pr-bot",
    "discovery_subject": "gh-pr-bot",
    "runtime_subject": "corpus/sim/rt-prbot-context-poisoning.git-scenario.json",
    "evidence_bundle": null,
    "expected": { "static_flagged": false, "runtime_dirty": true, "quadrant": "static_blind" } } ] }
```

### correlate.py -- pure, deterministic (I4)

`correlate(discovery_scorecard, behavior_reports, links, thresholds) -> CorrelationReport`.
No clock, no random, sorted/stable serialization -> byte-identical on replay.

- `static_flagged` derives from INVARIANT discovery properties only -- the repo's
  position in the discovery risk ORDER (top-K) plus high-risk action_pattern /
  policy presence. NEVER the opaque static score (respects the discovery
  ground-truth rule).
- `runtime_dirty` = `behavioral_score` > `thresholds.runtime_dirty` (an explicit
  knob, captured in provenance -- I4).
- Quadrant = binary x binary. Clean and replayable.

### CorrelationReport shape

```
{ rows: [{agent_id, static_flagged, runtime_dirty, quadrant, agreement}],
  quadrants: {agree_clean:int, agree_dirty:int, static_blind:[ids], static_overflag:[ids]},
  unresolved: [{agent_id, reason}],          # fail-loud: never a phantom quadrant
  coverage_gaps: [{discovery_subject}],      # a discovery subject with no link
  provenance: {discovery_hash, evidence_hashes:[...], thresholds, tool_version} }
```

`correlation_id = sha256(discovery_hash + evidence_hashes + thresholds + tool_version)`
= the citable experiment identity.

## Data flow

```
discovery scorecard ┐
                    ├─ correlate(links, thresholds) ─> CorrelationReport ─> CLI / API / Console
behavior reports ───┘
```

## Error handling / failure modes (fail-loud, never silent)

| Case | Behavior |
|------|----------|
| link `discovery_subject` not resolvable | `unresolved[]` reason `discovery_missing`, excluded from quadrants |
| link has no runtime evidence (common at P1) | `unresolved[]` reason `evidence_missing`, excluded -- NOT a crash |
| discovery subject with no link at all | `coverage_gaps[]` -- visible, not swallowed (coverage-guard ethos) |
| threshold absent | explicit versioned default in the profile, never `now()`/hidden heuristic |

A missing coupling is a visible red line, never a phantom quadrant. Aligned with
the no-silent-recette-gaps lesson and the coverage guard.

## UI Lux -- first-class P1 deliverable (the steering wheel + windshield)

`CorrelationPanel.tsx` in Probe, modeled on the existing `BehaviorWavePanel`,
using `probe.css` theme tokens (no hardcoded colors, theme-aware):

- **2x2 quadrant grid**, cells clickable; `static_blind` rendered in the alert
  accent (the cell that matters).
- **static_blind drill-in** -- click -> the source-clean / runtime-dirty agents;
  each agent opens its three-way (PLANNED/SAID/DONE) + OWASP/ATLAS findings.
- **threshold knobs** -- edit `runtime_dirty` live, re-run, quadrants move.
- **provenance banner** -- copyable `correlation_id` = citable artifact.
- **visible gaps** -- `unresolved[]` + `coverage_gaps[]` rendered in clear
  (fail-loud on the UI too, not masked).
- Built with the `frontend-design` skill; R16 contract gate (real fixture +
  render-and-assert; cover the `static_blind` quadrant render).

Rationale (operator, 2026-06-25): shipping the engine without the console is "a
car without a steering wheel and windshield". The panel ships in P1.

## Testing (R20 gates)

- `tests/test_behavior_correlate.py` -- fixtures (discovery scorecard + behavior
  reports + links) -> assert exact quadrant classification, assert `unresolved`
  counted, **replay byte-equality** (I4).
- `tests/test_api_behavior.py` -- add `POST /behavior/correlate` (`[api]` extra).
- `CorrelationPanel.test.tsx` -- real captured fixture + render-and-assert,
  covers the `static_blind` quadrant (R16).
- coverage-guard (optional P1, hardened P3): a discovery subject with no link
  turns the guard yellow.

## Team runbook (`docs/runbooks/behavior-discovery-research.md`)

Day-to-day research flow:

1. `recette discovery` -> static risk.
2. Build evidence bundles (corpus-first, deterministic).
3. `recette analyze` waves -> runtime `behavioral_score`.
4. `recette analyze correlate` -> quadrant matrix; inspect `static_blind`.
5. Metrology: sweep thresholds -> ROC of "does static risk predict runtime
   behavior?"; ablation per lens; `export` the `correlation_id` = citable
   package.
6. Console: the Correlation panel in Probe (quadrants + static_blind list +
   provenance).

## Phasing

- **P1 (this design)**: `agent_links.json` + `correlate.py` + CLI + API +
  CorrelationPanel (Lux) + runbook, over existing pairable subjects, gaps
  documented.
- **P2**: discovery output (detected IDs) feeds a profile `cohort` selector.
- **P3**: 1:1 twin evidence bundles per discovery subject -> closes the gaps,
  coverage-guard hardened.

## Invariants touched

- I4 determinism: `correlate` is pure; replay test mandatory.
- R23: findings keep OWASP ASI 2026 + MITRE ATLAS tags through the drill-in.
- Discovery ground-truth rule: `static_flagged` uses invariant properties only,
  never the opaque static score.
