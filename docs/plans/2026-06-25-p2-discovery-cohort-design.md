# P2 -- Discovery-derived wave cohort -- design

Date: 2026-06-25
Status: APPROVED. Builds on P1 (behavior<->discovery correlation).

## Problem

A behavioral wave runs over every agent in the evidence bundle. A researcher
often wants to run it over exactly the set the DISCOVERY engine surfaced -- e.g.
"score only the agents the static scan flagged high-risk" (risk triage), or "scan
the behavior of the whole discovered fleet". Today the only cohort selector is a
manual `cohort.agents` list; there is no bridge from a discovery scan to that
list.

## Core idea

Derive the wave's `cohort.agents` from a discovery scan, through the P1 identity
map. The behavioral engine stays UNCHANGED (its `_cohort_match` already filters
on `cohort.agents`); a pure edge-resolver fills that list from discovery. This is
the same edge-IO / pure-core split as P1.

## Components

### 1. Pure resolver (edge)

`discovery_cohort(links, mode, corpus_root=None) -> list[str]` in
`recette/behavior/correlate.py` (next to `build_discovery_facts`):
- runs `build_discovery_facts(links, corpus_root)` (P1, deterministic),
- `mode == "detected"` -> agent_ids whose discovery_subject is `detected`,
- `mode == "flagged"` -> agent_ids whose discovery_subject is `flagged`,
- returns the agent_ids SORTED (I4), de-duplicated.

### 2. Profile carries the intent, edge resolves it

`AnalysisProfile.cohort` gains an optional key `discovery: "detected"|"flagged"`.
The ENGINE does not read it. The EDGE (CLI / API), before `run_wave`, resolves it:

```
mode = profile.cohort.get("discovery")
if mode in ("detected", "flagged"):
    profile.cohort["agents"] = discovery_cohort(load_links(), mode)
```

So the engine still sees a plain `cohort.agents` list and stays pure +
byte-stable. An invalid mode is a 400 (API) / argparse error (CLI), never a
silent all-pass.

### 3. Surfaces

- **CLI**: `recette analyze wave --cohort-discovery detected|flagged` -- pre-
  resolves and injects `cohort.agents`, then runs the wave. Echoes the resolved
  cohort (mode + agent_ids + count) before the report (fail-loud).
- **API**: `/behavior/wave` and `/behavior/correlate` accept
  `profile.cohort.discovery`; the router resolves it via `discovery_cohort` and
  sets `cohort.agents` before building the bundle / running the wave. The
  response echoes the resolved cohort (`{"cohort": {"mode", "agents"}}`).
- **UI**: `BehaviorWavePanel` gains a cohort selector **All / Discovered /
  Flagged** that sets `cohort.discovery` (or clears it for All) in the profile it
  posts. The resolved cohort + count render above the report.

## Fail-loud (R13)

- The resolved cohort is always surfaced (mode + agent_ids + count) in CLI stdout,
  API response, and UI.
- If the resolved cohort matches NO runtime agent in the bundle (the P1 agent_id
  mapping frontier), the wave runs over nobody and that is rendered explicitly
  ("cohort: flagged -> [admin-overreach]; 0 matched in evidence"), never a blank
  success.

## Determinism (I4)

`discovery_cohort` is deterministic (the reference scan is). The engine is
unchanged, so a wave with a resolved cohort is still byte-identical on replay.
Replay test: same links + same mode -> same cohort list.

## Testing (R20)

- `tests/test_behavior_correlate.py`: `discovery_cohort` returns the right
  detected-set and flagged-set over the corpus; sorted + deduped; replay-stable.
- `tests/test_api_behavior.py`: a wave with `cohort.discovery="flagged"` filters
  the agents (the report's agent set is a subset; the resolved cohort is echoed).
- console: `BehaviorWavePanel.test.tsx` -- the selector renders and posting with
  "Flagged" sends `cohort.discovery="flagged"`.

## Docs + help (P1 lesson -- definition of done)

- Update `docs/runbooks/behavior-discovery-research.md` (fr) + the en mirror with
  a P2 "cohort from discovery" section; `./recette.sh docs-build` green.
- Add a sentence to the `probe` help topic noting the cohort selector.

## Out of scope (P3)

1:1 twin evidence bundles per discovery subject -- closes the "0 matched" frontier
so a flagged cohort actually has runtime evidence to score.
