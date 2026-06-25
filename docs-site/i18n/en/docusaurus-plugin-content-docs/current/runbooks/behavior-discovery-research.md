# Behavior <-> Discovery Correlation -- research runbook

> For the AI-research team. How to use the platform to analyze agent BEHAVIOR
> (what an agent does at runtime) in relation to the DISCOVERY engine (what its
> source declares), and read the disagreement between the two.

## The mental model -- discovery PREDICTS, behavior MEASURES

Two engines look at the same agent from opposite ends:

- **Discovery** reads SOURCE (`corpus/repos/<slug>`, a static publishable repo).
  It is a STATIC risk predictor: detection, action_pattern, target, relative
  risk order, policy presence. Ground-truth is invariant properties only -- never
  an opaque score.
- **Behavioral-analysis engine** reads RUNTIME evidence (ebpf / proxy /
  action-log bundles). It MEASURES what the agent actually did: egress, dns,
  credential, doh, process, said-vs-done, and a `behavioral_score`.

The research value is the agreement -- and especially the disagreement -- between
the static prediction and the runtime measurement:

|                  | runtime clean   | runtime dirty                          |
|------------------|-----------------|----------------------------------------|
| source low-risk  | agree_clean     | **static_blind** (scanner false negative) |
| source high-risk | static_overflag | agree_dirty                            |

`static_blind` -- a source the scanner called clean that behaves dirty at runtime
-- is the headline signal. It is where a static-only review would have missed a
real threat.

## The identity map -- `corpus/agent_links.json`

Discovery subjects and runtime subjects are distinct corpus objects. They are
joined by `corpus/agent_links.json`: one entry per `agent_id`, naming its
`discovery_subject` (a repo) and its `runtime_subject` / `evidence_bundle`. This
is hand-maintained ground-truth until 1:1 twin evidence bundles exist (P3). A
link with no resolvable discovery subject or no runtime evidence is reported
loud (`unresolved[]`), never silently dropped.

## Day-to-day flow

1. **Static risk** -- run the discovery scorecard:
   ```
   python3 -m recette discovery --adapter reference
   ```
   This is the source-side prediction (per-repo detection + relative risk order).

2. **Runtime evidence** -- build / refresh evidence bundles (corpus-first,
   deterministic) and run behavioral waves:
   ```
   python3 -m recette analyze wave --evidence <bundle> --profile <profile.json>
   ```
   Each wave is pure (I4): same `(evidence, profile)` -> byte-identical report.

3. **Correlate** -- join the two engines through the identity map:
   ```
   python3 -m recette analyze correlate
   ```
   Prints the quadrant matrix. Read the `static_blind` line first. `unresolved`
   and coverage-gap lines show exactly which links could not be resolved at the
   current corpus state (the honest P1 boundary).

4. **Inspect static_blind** -- for each agent in that quadrant, open its
   three-way (PLANNED / SAID / DONE) and its OWASP ASI 2026 + MITRE ATLAS
   findings to see WHAT it did that the source scan missed.

5. **Metrology** -- turn a correlation into a measurement:
   - `python3 -m recette analyze sweep ...` -- vary a knob (e.g. the
     `runtime_dirty` threshold) -> ROC of "does static risk predict runtime
     behavior?".
   - `python3 -m recette analyze ablate ...` -- per-lens detection delta.
   - `python3 -m recette analyze export ...` -- a citable experiment package.
     The correlation carries its provenance (`tool_version`, `thresholds`) so a
     result is reproducible.

6. **Console** -- the Probe page hosts the **Correlation panel**: the 2x2
   quadrant grid (static_blind in the alert accent), a `runtime_dirty` threshold
   knob that re-runs the correlation live, the provenance line, and an explicit
   unresolved / coverage-gap block. Drill into a quadrant cell to see its agents.

## Cohort from discovery (P2)

By default a behavioral wave runs over all agents present in the evidence bundles.
P2 lets you restrict that cohort to the agents a discovery scan retained, in two
modes:

- **detected**: every agent the scanner detected (all visible repos).
- **flagged**: only agents the scanner marked as high-risk (elevated risk level or
  sensitive action patterns).

### CLI

```
python3 -m recette analyze wave --evidence <bundle> --profile <profile.json> --cohort-discovery detected
python3 -m recette analyze wave --evidence <bundle> --profile <profile.json> --cohort-discovery flagged
```

The resolver reads the identity map (`corpus/agent_links.json`) and the reference
discovery scan, then injects the retained `agent_id` list into the profile before
launching the wave. The output always prints the cohort echo:
`cohort: flagged -> [admin-overreach, ...] (N)`. This is fail-loud by design: if the
mode matches no agent, the list is empty and the count is explicitly zero -- never a
silent success.

### API

Pass `cohort.discovery` in the profile submitted to `/behavior/wave`:

```json
{
  "recording": "...",
  "profile": {
    "threat": "exfil",
    "cohort": { "discovery": "flagged" }
  }
}
```

The response includes a `cohort` field with the resolved mode and agent list:

```json
{
  "cohort": { "mode": "flagged", "agents": ["admin-overreach"] }
}
```

An unknown value (neither `detected` nor `flagged`) returns a 400 error.

### Console

The **Behavioral analysis** panel on the Probe page exposes a cohort selector:
**All** (default behavior, all agents in the evidence), **Discovered** (`detected`
mode), and **Flagged** (`flagged` mode). After a run in `Discovered` or `Flagged`
mode the panel displays the line `cohort: {mode} -> N agent(s)` with the resolved
list.

### P1 boundary -- "0 matched"

A `flagged` cohort contains the `agent_id`s that the identity map could resolve from
the discovery scan. If none of those `agent_id`s has runtime evidence in the supplied
bundle, the wave runs over zero agents and the echo says so explicitly. This is
expected in P2 -- the 1:1 twins between discovery subjects and runtime bundles are
built in P3. Until then, a `flagged` cohort may match no agent in the current bundle;
that is the honest, visible frontier, never hidden.

## Reading the result honestly (P1 boundary)

At P1 the identity map pairs the subjects that already exist on both sides;
links without runtime evidence show as `evidence_missing` in `unresolved[]`. That
is expected and visible by design -- it is not a bug, it is the coverage frontier.
P2 lets a discovery scan feed a wave cohort directly; P3 builds 1:1 twin evidence
bundles per discovery subject and closes the gaps (the coverage guard then turns
red on any unlinked discovery subject).

## Determinism and provenance (why this is publishable)

- `correlate` is a pure function of `(discovery_facts, behavior_reports, links,
  thresholds)` -- no clock, no random, sorted output, byte-identical on replay
  (I4). The reference discovery scan is itself deterministic.
- `static_flagged` is derived from invariant discovery properties (detection +
  risk level + action_pattern), never an opaque static score -- so the
  correlation respects the discovery ground-truth rule.
- Every correlation reports its `thresholds` + `tool_version`, so a quadrant
  assignment is reproducible and citable.

## 1:1 twins (P3)

P3 closes the P1/P2 frontier by giving every detected discovery subject a
**frozen evidence twin** (`corpus/evidence/<subject>/bundle.json`). All eight
detected subjects (four per surface: github and gitlab) have a twin; the two
no-agent subjects (`no-agent-gh`, `no-agent-gl`) do not.

### Twin structure

Each twin is a frozen `EvidenceBundle` whose `recording.agent_id` matches
exactly the `agent_id` declared in `corpus/agent_links.json`. The wire recipe
is chosen to produce the intended quadrant deterministically (I4):

| subject (gh and gl) | quadrant |
|---------------------|----------|
| readonly-reporter | agree_clean |
| pr-bot | static_blind |
| supply-chain-compromise | static_overflag |
| admin-overreach | agree_dirty |

Verified output of `python3 -m recette analyze correlate`:

```
agree_clean=2  agree_dirty=2  static_blind=2  static_overflag=2
  pr-bot-gh ... -> static_blind ; admin-overreach-gh ... -> agree_dirty
  readonly-reporter-gh -> agree_clean ; supply-chain-gh -> static_overflag
  no-agent-gh: evidence_missing
```

All four quadrants are demonstrably covered; the two no-agent subjects remain
as `evidence_missing` (fail-loud, never in a phantom quadrant).

### `analyze correlate` without a live probe

From P3 onward, `python3 -m recette analyze correlate` populates the quadrants
from the corpus alone, with no live eBPF capture. The `correlate_corpus`
function loads each twin, runs a pure behavioral wave (I4), and feeds the
existing correlate. The command produces a byte-identical result on replay
(same (twin, profile) -> same report).

### Coverage guard (fail-loud)

The test `tests/test_behavior_link_coverage.py` is the lock: it turns **red**
whenever a discovery subject has no entry in `corpus/agent_links.json`, a link
points to an `evidence_bundle` whose recording `agent_id` does not match the
link, or the quadrant produced by the wave diverges from the `expected.quadrant`
declared in the link. The two twin-less subjects (`gh-no-agent`, `gl-no-agent`)
are frozen in an explicit constant -- their count cannot grow silently.

## Related

- `docs/plans/2026-06-25-behavioral-analysis-engine-design.md` -- the behavioral
  engine (evidence bundles, profiles, lenses, research layer).
- `docs/plans/2026-06-25-behavior-discovery-correlation-design.md` -- this
  correlation design (approach A, phasing).
- `.claude/rules/recette-corpus.md` -- the three forms of an agent (runtime /
  identification / discovery) and why discovery never sees the runtime.
- `.claude/rules/redteam-standards-alignment.md` (R23) -- the OWASP ASI 2026 +
  MITRE ATLAS tags the findings carry.
