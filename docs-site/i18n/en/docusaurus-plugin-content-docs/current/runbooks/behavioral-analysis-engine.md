# Behavioral-analysis engine -- runbook

> The behavioral-analysis engine turns the three-way reading of an agent
> (PLANNED vs SAID vs DONE) into a **measurement instrument**: an analyst runs
> tunable *waves* over *frozen evidence* and gets a deterministic, **replayable**
> verdict (I4). Same evidence + same profile = the same report, byte-for-byte -- a
> researcher reproduces the experiment exactly.

Design: `docs/plans/2026-06-25-behavioral-analysis-engine-design.md`.
Code: package `recette/behavior/` (`evidence.py`, `profile.py`, `lenses.py`,
`engine.py`, `report.py`), CLI `recette/cli/behavior_cmds.py`.

## The four objects

1. **EvidenceBundle (the replayable proof)** -- a frozen, content-addressed
   folder: `{ordered eBPF recording per agent, server-registry snapshot, declared
   plan per agent (scope / systems / decided actions), optional baselines,
   optional ground-truth}` + a `sha256` over a canonical serialization. Replaying
   a wave on the same bundle reproduces the report byte-for-byte
   (`recette/behavior/evidence.py`).

2. **AnalysisProfile (the wave -- 4 knobs)** -- what varies between waves:
   - `lenses` -- which detector families run (enable/disable);
   - `thresholds` -- per-lens severity / tolerance (`credential=alert|warn|off`,
     `ghost_host_tolerance=N`, `scope=strict|lax`);
   - `cohort` -- which agents enter the wave (`["*"]` = all);
   - `threat` -- a hypothesis that REWEIGHTS the lenses in the behavioral score
     (`neutral|exfil|escalation|tunneling|supply_chain`).
   The profile is hashed (`profile_hash`) for provenance.

3. **Lens registry (the detectors, pure)** -- each lens is a pure
   `(AgentContext, profile) -> findings`. The static detectors (egress, dns,
   credential, doh, process, said_scope) plus **two behavioral lenses** that make
   the difference:
   - **sequence** (temporal): the ORDER of events -- catches the exfil chain "read
     a secret THEN reach an undeclared host", which a set-based detector misses
     because each event alone looks benign;
   - **baseline** (novelty): deviation from a frozen fingerprint (a server never
     seen, connect volume above a ceiling). No-op when no baseline is provided (no
     false positive).
   Every finding carries a standards tag (R23): OWASP Top 10 Agentic 2026 + MITRE
   ATLAS (e.g. credential -> `ASI03` / `AML.T0055`, exfil chain -> `ASI02` /
   `AML.T0086`).

4. **AnalysisReport (the deterministic output)** -- per agent: the three-way, the
   sorted findings, a `behavioral_score` (100 minus the threat-weighted penalty,
   clamped to [0,100]), and provenance
   `experiment_id = evidence_hash | profile_hash | tool_version`.

## CLI

```
python3 -m recette analyze wave --evidence <bundle> [--profile p.json] [--threat exfil] [--json]
python3 -m recette analyze replay --evidence <bundle> [--profile p.json] [--threat exfil] --report prior.json
```

- `wave` runs a wave and prints a readable summary (or `--json` for the full
  report). `--threat` overrides the profile's hypothesis.
- `replay` re-runs the wave and asserts the report is **byte-identical** to the
  given report -- the reproducibility proof. Output `REPLAY OK` (exit 0) or
  `REPLAY MISMATCH` (exit 1).

`--evidence` accepts a bundle folder (`bundle.json`) or a direct JSON file.

## Research layer (P2) -- measure, not just detect

When the bundle carries `ground_truth` (`expected_verdict: correct|incorrect`),
the wave becomes a measurement instrument:

```
python3 -m recette analyze metrics --evidence <bundle> [--threat exfil] [--json]
python3 -m recette analyze sweep   --evidence <bundle> --knob ghost_host_tolerance --values 0,1,2,3
python3 -m recette analyze ablate  --evidence <bundle> [--threat exfil]
python3 -m recette analyze export  --evidence <bundle> --out <pkg>
```

- **metrics**: confusion matrix (TP/FP/FN/TN, precision/recall/F1), **separation
  AUC** (is a POSITIVE scored more suspicious than a NEGATIVE?), **ROC curve** over
  the score cutoff, and **standards distribution** (OWASP/ATLAS).
- **sweep**: sweeps a threshold knob and prints the confusion at each setting --
  the dose-response for finding the operating point (e.g. ghost-host tolerance
  0->3 drops recall once the single-host leak is tolerated).
- **ablate**: removes each lens and measures the detection delta -> each lens'
  quantified contribution (a lens whose removal drops TP is pulling its weight;
  one that only drops FP is a noise source).
- **export**: writes a self-contained **experiment package** (`evidence/`,
  `profile.json`, `report.json`, `metrics.json`, `README`) reproducible via
  `analyze replay` -- a researcher's citable artifact.

Label convention: `expected_verdict = "incorrect"` = POSITIVE (should be detected);
`"correct"` = NEGATIVE (should stay clean); an unlabeled agent is excluded from
the metrics.

## Determinism (I4)

No clock / random / IO in a lens or the runner: the baseline and the frozen
evidence are INPUTS. `replay` asserts byte-equality -- both the researcher's
reproducibility guarantee and a regression test (`tests/test_behavior_engine.py`,
`tests/test_behavior_cli.py`).

## Varying the waves (recette / research)

On the SAME bundle, replay several profiles to answer different questions:

- sensitivity: vary `thresholds.ghost_host_tolerance` or `credential` -> observe
  the effect on divergences;
- ablation: remove a lens from `lenses` -> measure its contribution;
- hypothesis: change `threat` -> "analyze under the exfil vs escalation angle";
- cohort: restrict `cohort.agents` -> focus on a subset.

> Next phases (design): P2 research layer (ground-truth confusion matrix, ROC
> sweep, quantified ablation, exportable experiment package, separation score);
> P3 console "Behavioral analysis" panel (4-knob editor, side-by-side wave compare,
> download the proof).

## Links

- `.claude/rules/redteam-standards-alignment.md` (R23) -- OWASP/ATLAS mapping.
- `.claude/rules/determinism-replay.md` (I4) -- replay obligation.
- `docs/runbooks/surface-detection-recette.md` -- the three-way reading on the probe side.
