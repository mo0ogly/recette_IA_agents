# P3 -- Twin evidence bundles + hard coverage guard -- design

Date: 2026-06-25
Status: APPROVED (full-corpus scope, red-on-unlinked guard). Closes the P1/P2 "0 matched" frontier.

## Problem

After P1 (correlation) and P2 (cohort), `analyze correlate` still returns empty
quadrants live: no runtime recording carries an agent_id matching a link, so
every link is `evidence_missing`. The headline `static_blind` quadrant never
populates. P3 closes this by giving every DETECTED discovery subject a frozen 1:1
runtime evidence bundle (a "twin"), wiring `correlate` to run waves over those
twins (no live probe needed), and hardening the coverage guard so an unlinked
discovery subject is a RED test.

## Corpus shape (verified)

Two discovery surfaces, 5 subjects each (10 total, 8 detected):
- github: `corpus/repos/` -- gh-{admin-overreach, no-agent, pr-bot, readonly-reporter, supply-chain-compromise}
- gitlab: `corpus/gitlab/` -- gl-{same five}

Verified reference risk levels (max_level): admin-overreach=3, supply-chain=3,
pr-bot=2, readonly-reporter=1, no-agent=0 (both surfaces). The P1 `flagged`
derivation (`level > lower-median of detected levels`; median over the 8 detected
= 2) therefore flags **admin-overreach** and **supply-chain**, and leaves
**pr-bot** and **readonly-reporter** unflagged. This split is what makes all four
quadrants reachable.

## Twin design -- one frozen EvidenceBundle per detected subject

A twin lives at `corpus/evidence/<subject>/bundle.json` (a frozen
`EvidenceBundle`: `{recording, servers, declared, baselines, ground_truth}` +
`hash`). Its `recording.recordings[].agent_id` equals the link's `agent_id`. The
wire (`surfaces.ebpf_wire`, events like `open:/path` / `connect:ip:port`) +
`declared` plan are authored so a wave produces the intended quadrant given the
subject's static `flagged` value:

| subject (gh & gl) | discovery flagged | twin runtime wire | quadrant |
|-------------------|-------------------|-------------------|----------|
| readonly-reporter | no (lvl 1)        | in-scope only, no credential | **agree_clean** |
| pr-bot            | no (lvl 2)        | credential open + undeclared egress | **static_blind** |
| supply-chain      | yes (lvl 3)       | in-scope wire (compromise is in CI/source, not runtime) | **static_overflag** |
| admin-overreach   | yes (lvl 3)       | credential open + undeclared egress | **agree_dirty** |

no-agent (gh, gl): `detected=false`, NO twin; the link entry records it
(`evidence_bundle=null`, `expected.detected=false`) so the guard sees it is
deliberately twin-less.

The twin's behavior is a deterministic fixture (R4, explicit corpus fixture). Its
acceptance test is a wave: `run_wave(bundle, default_profile)` must yield the
intended `runtime_dirty` side, which combined with the static flag gives the
quadrant above. Authoring is verified against the lens code
(`recette/behavior/lenses.py`) -- credential/egress lenses fire on
`open:.../credentials` / out-of-scope `connect:`; clean = egress only to declared
servers, no credential opens.

## Surface-aware discovery facts (change to a P1 function)

`build_discovery_facts` currently scans only `corpus/repos` (github). P3 makes it
surface-aware: each `agent_links.json` link gains `surface: "github"|"gitlab"`,
and the resolver uses `SURFACE_CORPUS[surface]` to find the repo tree. The
`flagged` median is computed over ALL detected linked subjects across both
surfaces (deterministic). `discovery_cohort` (P2) inherits this for free.

## Offline correlate -- quadrants from frozen twins, no live probe

New pure-ish edge function `correlate_corpus(links, thresholds, corpus_root=None)`
in `recette/behavior/correlate.py`:
- builds surface-aware `discovery_facts`,
- for each link with an `evidence_bundle`, loads the frozen bundle, runs a wave,
  takes the agent's report -> `behavior_reports[agent_id]`,
- calls the existing pure `correlate(...)`.

So `analyze correlate` (CLI + API) finally returns populated quadrants from the
corpus alone. The live-recording path (P1) stays for the probe page; the corpus
path is the default for `recette analyze correlate` with no recording. Both feed
the same pure `correlate`. Determinism: every twin wave is byte-stable (I4), so
`correlate_corpus` is replay-stable; a replay test asserts it.

## Hard coverage guard (red on unlinked)

A new test (the coverage-guard family) asserts, across BOTH surfaces:
1. Every subject dir under `corpus/repos` and `corpus/gitlab` has a link in
   `agent_links.json` (an unlinked subject = RED).
2. Every link's `discovery_subject` exists on its declared `surface`.
3. Every link whose subject is DETECTED has an `evidence_bundle` that exists,
   loads as an `EvidenceBundle`, and whose recording carries the link's
   `agent_id` (a twin that does not match its link = RED).
4. Every twin wave produces the quadrant its link declares in `expected.quadrant`
   (the corpus stays self-consistent).

A frozen exceptions constant (like the existing guard) lists deliberately
twin-less subjects (the two no-agent), so they cannot grow silently.

## UI

The CorrelationPanel already renders quadrants. With twins, the live page (after
a probe capture that happens to include a linked agent) and the CLI/API now
populate `static_blind` etc for real. No new component; verify the populated
state renders (a fixture captured from `correlate_corpus`).

## Testing (R20)

- `tests/test_behavior_correlate.py`: `correlate_corpus` populates the four
  quadrants over the corpus; replay byte-identical; surface-aware facts flag the
  right subjects.
- coverage guard test (above) -- red on unlinked / mismatched twin.
- `tests/test_api_behavior.py`: `/behavior/correlate` with no recording (corpus
  mode) returns populated quadrants.
- Each twin: an acceptance assertion (wave -> intended quadrant).

## Docs + help (definition of done)

- Runbook fr + en: a "Jumeaux 1:1 (P3)" section -- twins close the frontier,
  `analyze correlate` now populates from corpus, the guard is red-on-unlinked.
- Help: one sentence in the probe topic noting correlation now works without a
  live capture (corpus twins).

## Determinism / invariants

- Twins are frozen fixtures; waves over them are pure (I4). `correlate_corpus`
  replay-stable.
- `static_flagged` still derived from invariant discovery properties only.
- Mono-axis is not in play here (twins are evidence, not mono-axis negatives);
  the quadrant is an emergent (static × runtime) classification, documented.
