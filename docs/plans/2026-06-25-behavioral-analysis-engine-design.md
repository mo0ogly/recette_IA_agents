# Behavioral-Analysis Engine -- design (research-grade discovery tool)

Date: 2026-06-25
Status: APPROVED (approach B, research-grade), phased P1->P3.

## Problem

The per-agent three-way analysis (PLANNED vs SAID vs DONE, in
`recette/surface/agent_analysis.py`) is reachable only through the probe API /
console. There is no CLI tool, no replay harness, no way to vary the analysis,
and no measurement layer. An analyst/researcher cannot run a *powerful,
parametrable, replayable* behavioral analysis over agent evidence. This design
turns the detector into a **measurement instrument**.

## Core idea

An **engine** that runs tunable *waves* over *frozen evidence* and produces
deterministic, replayable, ground-truth-scored reports. Pure (I4): a wave is a
function of `(evidence, profile)`; same inputs -> byte-identical output.

## Components

### 1. Evidence bundle (the replayable proof)

A frozen, content-addressed folder:
`{ ebpf recording, proxy traces, action-logs, declared-registry snapshot,
ground_truth (optional) }` + a `sha256` over a canonical serialization. A wave
run records `evidence_hash`. Re-running on the same bundle reproduces the report
byte-for-byte. Bundles are built from a probe capture, a corpus subject, or a
campaign run.

### 2. AnalysisProfile (the wave -- the four knobs)

```json
{
  "name": "exfil-strict",
  "lenses": ["egress","dns","credential","doh","process","said_scope","sequence","baseline"],
  "thresholds": {"credential":"alert","doh":"alert","ghost_host_tolerance":0,"scope":"strict"},
  "cohort": {"agents":["*"],"campaign":null,"surfaces":["ebpf","proxy","action_log"],"window":null},
  "threat": "exfil"
}
```

- `lenses` -- active detector families (enable/disable).
- `thresholds` -- per-lens severity / tolerance.
- `cohort` -- which agents / campaign / surfaces / window enter the wave.
- `threat` -- a named weighting profile (exfil / escalation / tunneling /
  supply_chain) that reweights lenses and defines what counts as divergence.

The profile is hashed (`profile_hash`) for provenance.

### 3. Lens registry (pluggable, pure `(evidence, params) -> findings`)

Each lens is a pure function returning findings `{lens, agent_id, severity,
log, why, owasp_asi, mitre_atlas}`. Today's detectors become lenses (egress,
dns, credential, doh, process, said_scope). Two NEW behavioral lenses provide
the depth:

- **sequence** -- order of DONE vs SAID: egress-before-read (injection tell),
  credential-read -> egress (exfil chain). Temporal = behavioral.
- **baseline** -- agent wire fingerprint vs a frozen per-role baseline: novelty
  (new server, volume spike). Deterministic against the stored baseline.

A finding carries a standards tag (R23: OWASP ASI 2026 + MITRE ATLAS).

### 4. Wave runner -> AnalysisReport

Applies a profile to a bundle: per-agent three-way + findings + a behavioral
score + provenance `{evidence_hash, profile_hash, tool_version}`. Pure.

### 5. Research layer

- **Ground-truth metrics**: confusion matrix (TP/FP/FN/TN) per lens / per threat
  when the bundle carries `ground_truth`.
- **Sweep -> ROC**: vary one knob across a range, plot detection vs
  false-positive; export CSV/JSON.
- **Ablation**: re-run with each lens removed -> delta detection per lens
  (`--ablate`).
- **Experiment package**: `evidence_hash + profile_hash + tool_version =
  experiment_id`; `export` writes a self-contained citable artifact.
- **Separation score**: per threat profile, how cleanly the behavioral score
  separates corpus positives from negatives (AUC-style).

### 6. Surfaces

- **CLI**: `recette analyze --evidence <b> --profile <p.json>` (report+JSON);
  `recette analyze sweep --profiles a,b,c` (wave diff); `recette analyze replay
  <report>` (byte-equality assert); `recette analyze export <report>`.
- **Console**: Probe gains a **Behavioral-Analysis** panel -- edit the 4 knobs,
  run a wave, per-agent three-way + score, side-by-side wave compare, ROC plot,
  download proof (R16 contract gate).

## Determinism (I4)

No clock / random / IO in any lens or the runner. The logical clock and frozen
evidence are inputs. `replay` asserts byte-equality -- this is the research
reproducibility guarantee, and a regression test.

## Phasing (each phase fully gated before the next)

- **P1** engine core: evidence bundle (+hash), AnalysisProfile (+hash), lens
  registry (port current detectors + add sequence & baseline), wave runner,
  deterministic report, replay. CLI `analyze` / `replay`. Unit tests + replay
  test.
- **P2** research layer: ground-truth metrics, `sweep` (ROC), `--ablate`,
  `export` package, standards tags surfaced, separation score. Unit tests +
  golden metrics.
- **P3** console Behavioral-Analysis panel: 4-knob editor, run wave, per-agent
  three-way + score, side-by-side compare, ROC plot, download proof. R16
  contract gate + render-and-assert.

## Invariants touched

I4 (determinism/replay -- the whole engine), I5 (evidence comes only from
mediated proxy/probe surfaces), R20 (zero-install tests), R23 (standards tags),
R16 (P3 console gate).

## Out of scope (YAGNI)

Live learning / online baselines (baseline is a frozen artifact), a query
language, multi-tenant storage. Bundles are folders on disk; metrics are flat
JSON/CSV.
