# Runbook -- multi-agent orchestration recette (end-to-end, replayable)

> Diagrams (mermaid) of the record / replay / freeze model across agents, teams
> and campaigns: see [`replay-model.md`](replay-model.md).

The judged unit is a **team**: a set of participants with a declared structure.
Four orchestration styles, each grounded on a real microsoft/agent-framework
builder:

| style | builder | run shape | correctness (behavior axis) |
|-------|---------|-----------|------------------------------|
| `handoff` | `HandoffBuilder` | `hops` | starts at the start agent, within the termination bound, no loop |
| `sequential` | `SequentialBuilder` | `order` | executed order == declared participant order, each once |
| `concurrent` | `ConcurrentBuilder` | `order` | each declared participant runs exactly once |
| `group_chat` | `GroupChatBuilder` | `order` | bounded turns, no participant monopolises |
| `magentic` | `MagenticBuilder` | `order` | bounded rounds, no stall (same speaker selected >= 3 in a row) |

The four dimensions are judged by `recette.maf_orchestration.judge_orchestration`,
a pure function of `(team, run)` -- identical input replays to an identical
verdict (I4).

## Offline corpus (deterministic, CI)

```
python3 -m recette validate
python3 -m recette report
```

`report` scores `corpus/maf_orchestration/{correct,incorrect}/<slug>/`
(team.json + run.json + ground-truth.json) as the `orchestration` area of the
aggregate verdict. Each negative breaks exactly one dimension (its
`violation_type`).

## Live -> record -> replay -> freeze (Groq)

A live LLM drives `handoff` and `group_chat` teams (it chooses the route via
`handoff_to_<target>` / `speak_<participant>` tools and the agents' own tools).
The run is recorded, replayed deterministically, and judged.

```
export GROQ_API_KEY=...                                  # R8: key via env, never hardcoded
python3 scripts/run_orchestration_live_groq.py --model llama-3.3-70b-versatile
```

Per team it prints `decisions=<n> verdict=<correct|incorrect>` and asserts the
replay reproduces the recorded run.

### Single team, by hand

```
python3 -m recette orchestrate run corpus/maf_orchestration/correct/support-handoff-correct/team.json --provider groq --model llama-3.3-70b-versatile --out /tmp/run.json
python3 -m recette orchestrate replay /tmp/run.json
python3 -m recette orchestrate freeze /tmp/run.json --slug live-support-handoff --category correct --out corpus/maf_orchestration/correct
```

- `run` drives the team and writes an `OrchestrationRecording` (the team + the
  ordered LLM decisions + the produced run). Persistent and self-contained.
- `replay` re-drives the recording with a `ReplayLlm`: it reproduces the exact
  recorded run (a divergence is an error) and prints the verdict. Deterministic.
- `freeze` turns the recording into a corpus subject whose ground-truth is
  derived from the judge -- the dynamic run becomes a permanent deterministic
  recette case. Re-run `python3 -m recette validate` afterwards.

`sequential`/`concurrent` topologies are structural (no model needed to route);
they live in the offline corpus and `tests/test_orchestrate.py`.

### Visualize a team or a run

```
python3 -m recette orchestrate viz corpus/maf_orchestration/correct/support-handoff-correct/team.json
python3 -m recette orchestrate viz /tmp/run.json --run
```

`viz` prints a Mermaid `flowchart TD`: the team's declared structure per style
(handoff edges / sequential chain / concurrent fan-in / manager dotted edges for
group_chat & magentic), or, with `--run`, the actual routed path (numbered hops
or order, plus tool calls). Pure + deterministic (recette/viz.py), conventions
from agent-framework `_viz.py`.

## How it integrates with the defined recette + campaigns

- The orchestration corpus is part of the single release gate
  `python3 -m recette report` (alongside identification, MAF subjects and every
  discovery surface).
- The console **Corpus** page lists every subject across families
  (`git_agent` / `maf_agent` / `maf_orchestration`) from `GET /subjects`.
- The live runner sits in the existing `scripts/run_*_live_groq.py` family: a
  non-deterministic live demo whose deterministic proof is the offline corpus
  plus `tests/test_orchestrate.py` (record -> replay -> identical verdict).

## Invariants

- I3: a participant's tool call must use its declared `provider`/`model`.
- I4: the judge is pure; recordings replay identically.
- I6: an approval-gated tool (`approval: always`) must be approved before use.
