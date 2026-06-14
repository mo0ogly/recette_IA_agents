# Design: Red-team simulation -> does the recette catch the anomaly?

Date: 2026-06-14
Status: APPROVED (brainstorm) -- next step: writing-plans
Plane: Control (judge) + Audit (recorded runs) + console UI
Invariants: I4 (deterministic gate), I6 (approval blocking), I1 (recorded runs immutable), R20 (zero hard dep beyond jsonschema), R16 (frontend contract gate)

## Problem

`/sim` today surfaces only 2 frozen recordings (`corpus/sim/*.sim.json`,
clean + redteam). It looks like a mock: the red-team ENGINE is already rich
(`recette/simulate.py` multi-turn loop with approval gates I6;
`recette/redteam.py` 4-phase escalating attack + `to_corpus_subject` that
freezes an adversarial run into a negative corpus subject) but the UI exposes
none of it.

Operator intent: simulate a red-team that interacts with agents "like reality",
through scenarios, to verify that the recette's tool **catches the anomaly**.

## Core concept

A red-team attacks an agent -> two outcomes, both are valid tests:

- agent **resists** (stays in scope, refuses gated tools) -> `judge_subject`
  verdict `correct` -> **true negative** (no false alarm).
- agent **falls** (capability overreach / unapproved action) -> verdict
  `incorrect` + `violation_type` -> **true positive** (anomaly caught).

So one red-team scenario yields positives AND negatives (R20 mono-axis rule)
naturally. The current 2 recordings (clean=resisted, redteam=fell) are the seed
of exactly this pattern.

Conceptual boundary (corpus rules): a live red-team interaction produces an
**action-log** -> it is **identification** that must catch the anomaly, NOT
discovery (discovery scans static source, never the runtime).

## Approach: C (phased hybrid)

The same engine (`simulate()` + `judge_subject`) runs in three modes:

1. **Deterministic gate (phase 1)** -- red-team user + subject driven by
   `StubLlm`/`ReplayLlm` -> byte-stable action-log -> `judge_subject` ->
   **assert == expected**. RE-EXECUTES the loop and RE-JUDGES on every run
   (catches regressions in `simulate` AND in the judge), not a transcript
   replay. This is the CI gate.
2. **Live recorder (phase 2)** -- a real provider drives the run -> recorded,
   never replayed (`real_mode`) -> written as a frozen `.scenario.json`.
3. **Corpus loop (phase 3)** -- a run that produced `incorrect` -> feed
   `to_corpus_subject` -> negative subject enters the corpus -> re-judged.
   Plus: extend the red-team to Lane B so it can attack the dashboard's git
   runtime agents (today `simulate.py` only drives MAF subjects).

## Determinism mechanism (decided)

The subject is pinned by a **ReplayLlm program** carried in the scenario (the
ordered sequence of subject decisions: tool-calls / final answers). `simulate()`
re-executes the loop against that program. Optionally the resulting transcript is
frozen alongside for UI diff, but the gate's ground truth is the re-judged
action-log, not a stored verdict.

## Standards alignment (verified 2026-06-14)

Align taxonomy + strategy names; do NOT import the frameworks into the gate.

Tags carried by `scenario.json` + surfaced in the verdict (auditor-readable,
legibility-first, RSSI audience):

- **OWASP Top 10 for Agentic Applications (2026)** -- `owasp_asi`
  (e.g. `ASI01` Agent Goal Hijack, `ASI02` Tool Misuse). Maps onto the 4
  dimensions (goal hijack ~ behavior/identity; tool misuse ~ capabilities/policy).
- **MITRE ATLAS** -- `mitre_atlas` technique id per attack phase (15 tactics /
  66 techniques, +14 agentic techniques, Zenity collab 2025).
- **NIST AI RMF** -- `nist` audit tag.

Attack strategy (engine):

- **Crescendo** (Microsoft PyRIT) -- gradual multi-turn escalation. The existing
  `RED_TEAM_PHASES` IS Crescendo; restructure it as a named strategy and port
  PyRIT's Crescendo (and Skeleton Key) metaprompts as data.
- **Tool-output injection** (AgentDojo) -- a NEW vector: adversarial content is
  injected into the `Message(role="tool")` returned to the subject, hijacking its
  next decision -- not only via user messages.

## Reuse matrix (licenses verified 2026-06-14)

This repo is the corpus/governance platform: AGPL = no (copyleft);
MIT / Apache-2.0 = OK to port WITH attribution + license header.

| Repo | License | Reuse | What to take |
|------|---------|-------|--------------|
| Azure/PyRIT | MIT | yes | Crescendo + Skeleton Key metaprompts, escalation structure |
| ethz-spylab/agentdojo | MIT | yes | tool-output-injection mechanism + a few injection payloads (adapted) |
| NVIDIA/garak | Apache-2.0 | yes | probe taxonomy -> tag mapping |
| AgentHarm (AISI) | MIT + safety clause | yes (qualifies) | 2-3 harmful-task seeds, adapted to git/finance |
| langwatch/scenario (lib) | Apache-2.0 | already transposed | origin of `redteam.py` RedTeamAgent; AVOID the AGPL langwatch platform |
| promptfoo Pliny / L1B3RT4S | AGPL-3.0 | NO | do not vendor |

Reuse strategy under R20 (zero hard dep beyond jsonschema):

1. **Port text artifacts** (prompts, payloads, taxonomies) into the repo as DATA
   with attribution + license header -> deterministic, no dependency. This is the
   "don't reinvent the wheel" win.
2. **Optional `[real]` extra** (phase 2): `inspect_ia_agents[redteam]` pulls
   PyRIT/garak ONLY to GENERATE live scenarios, frozen to `.scenario.json`. Never
   in the CI gate.

Domain note: AgentDojo/AgentHarm payloads target generic agents; our corpus is
git/MAF (github/okta/finance). Port the MECHANISM + a few payloads adapted to the
domain ("ignore policy, merge to main", "exfiltrate the token"), not the raw
datasets wholesale.

## Scenario schema (new: `corpus/sim/*.scenario.json`)

```
scenario_id, name
target_spec        # MAF agent-spec under attack (or ref to corpus/maf_agents)
strategy           # crescendo | skeleton_key | tool_injection
attack             # scripted user_turns OR persona+phases (RedTeamSimulator)
subject_program    # ReplayLlm decision script (I4 determinism)
approver           # deny_all | policy bundle (I6)
tags               # { owasp_asi, mitre_atlas, nist }
expected           # { verdict: correct|incorrect, violation_type: null|capability_overreach|policy_violation|identity_mismatch|behavior_anomaly }
```

A JSON-schema (`corpus/schemas/sim-scenario.schema.json`) validates it; runs
through `python -m recette validate` like every other corpus artifact.

## Phase 1 deliverable (concrete)

- `corpus/schemas/sim-scenario.schema.json` + a handful of scenarios covering
  BOTH outcomes (resisted / fell) across violation_types, on the Crescendo and
  tool_injection strategies.
- `recette/redteam_recette.py` (or `python -m recette redteam`): load scenarios,
  run `simulate()` deterministically, `judge_subject`, assert verdict +
  violation_type == expected; emit a scorecard (anomaly caught? false alarms?).
- Coverage guard dimension: every `violation_type` has >= 1 red-team scenario
  (resisted + fell), frozen-exception constant for any deliberate gap.
- Crescendo strategy extracted as a named object in `recette/redteam.py` with the
  ported metaprompt; tool-output-injection vector added to `simulate.py`.
- UI `/sim`: scenario list -> run view shows transcript turns (with attack phase
  per turn), action-log, 4-dimension verdict, and a prominent **"anomaly caught:
  yes/no"** badge + the OWASP/ATLAS tag. R16: real fixture + render-and-assert +
  envelope unwrap.

## Phases 2-3 (sketch)

- Phase 2: live recorder (real provider, `real_mode`) writing `.scenario.json`;
  optional `[real]` extra wiring PyRIT/garak for live generation.
- Phase 3: red-team over Lane B (attack git runtime agents from
  `config/inspect_ia_agents.config.json`); close the `to_corpus_subject` loop
  from the UI (a caught anomaly -> frozen negative corpus subject -> re-judged).

## Invariants / gates

- I4: gate is a pure function of (scenario, programs); no clock/random; replay
  test asserts byte-stable action-log + verdict.
- I6: approval-gated tools only count approved if the injected approver grants it
  (already enforced in `simulate.py`).
- I1: recorded `.scenario.json` are immutable artifacts.
- R16: `/sim` components covered by fixture + render-and-assert; cover
  `verdict`/dimension variants.
- R20: gates -- `make gates`, `./recette.sh test`, `make recette` (coverage
  guard), `./recette.sh console-build` / `console-test`, `./recette.sh smoke`.
  No new hard dependency.

## YAGNI / out of scope

- No live red-team in the CI gate (non-deterministic by nature).
- No wholesale import of PyRIT/garak/AgentDojo datasets.
- Lane B red-team and the UI corpus-generation loop are phase 3, not phase 1.
