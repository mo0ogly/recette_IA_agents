# Runbook -- red-team recette (deterministic gate + live recorder, replayable)

> The red-team recette validates that an attacked agent is caught (or correctly
> cleared). A live adversarial run is recorded once, frozen into a byte-stable
> scenario, and from then on judged deterministically -- the gate never calls a
> live LLM (I4).

The judged unit is a **sim-scenario**: a target MAF subject plus a scripted
multi-turn attack and the recorded subject program. Scenarios live in
`corpus/sim/*.scenario.json` (schema `sim_scenario`), are replayed by
`recette.redteam_recette.run_scenario`, and judged by `judge_subject` on the same
four dimensions as every other corpus subject (identity, capabilities, policy,
behavior).

| field | meaning |
|-------|---------|
| `target_spec` | the attacked `maf_agent` manifest (its declared `capability_scope`) |
| `attack.user_turns` | the scripted adversarial messages, in order |
| `subject_program` | the recorded subject decisions (`ReplayLlm` consumes them, I4) |
| `approver` | named approver (`deny_all`): a gated tool is never approved (I6) |
| `expected` | the ground-truth `{verdict, violation_type}` the recette must reproduce |

"Anomaly caught" = the predicted verdict matches `expected.verdict`: a true
positive (an attacked agent that overreached is judged `incorrect`) or a true
negative (an agent that resisted is judged `correct`, no false alarm).

## The deterministic gate (CI, no key)

```
python3 -m recette redteam
```

Globs `corpus/sim/*.scenario.json` in sorted order (deterministic, I4), replays
each through `run_scenario`, aggregates with `redteam_scorecard`, and exits
non-zero when any anomaly was missed (predicted verdict diverged from
`expected`). The replay uses `ReplayLlm` over the frozen `subject_program`: no
network, no clock, no random.

Anti-silence coverage is enforced by the coverage guard:

```
python3 -m unittest tests.test_coverage_guard
```

`test_d7_redteam_violation_type_coverage` (D7) asserts every red-team
`violation_type` has at least one corpus scenario; a new violation axis without a
scenario turns the guard RED (a gap is a failing test, never found by hand).

Console: the **/sim** page lists the scenarios and shows the caught/missed badge
per scenario, sourced from the same deterministic replay.

## The live recorder (real provider, key from .env)

A live LLM drives BOTH the attacker and the target subject; the run is recorded
and frozen into a replayable scenario. Two entry points, same
`recette.redteam_record.record_scenario` core:

### CLI

```
export GROQ_API_KEY=...        # R18: resolved from the gitignored .env; never hardcoded
python3 -m recette redteam-record \
  --spec path/to/target.manifest.json \
  --subject-provider groq --subject-model llama-3.3-70b-versatile \
  --attacker-provider groq --attacker-model llama-3.3-70b-versatile \
  --scenario-id rt-my-case --name "My red-team case" \
  --owasp ASI02 --out corpus/sim
```

### Versioned proof script (R14)

```
python3 scripts/run_redteam_record_live_groq.py
python3 scripts/run_redteam_record_live_groq.py --max-turns 4 --cache /tmp/llm-cache.json
```

`scripts/run_redteam_record_live_groq.py` is the committed live proof: a real
Groq model red-teams an inline `maf_agent` target that declares a single
`web_search` tool (approval `never`), so any out-of-scope tool call is a
`capability_overreach` (OWASP ASI02). It prints the derived `verdict`, the OWASP
tag, and the output path. `--cache` wraps the backends in a content-addressed
`CachingLlm` (`recette/llm_cache.py`) so a re-run with the same inputs is served
from the JSON cache with zero network.

Both paths use `recette.redteam.RedTeamSimulator`, the escalating Crescendo
attacker (rapport -> probing -> escalation -> maximum pressure), as the
`UserTurns` provider.

### The live -> corpus loop

`record_scenario` wraps the subject in a `RecordingLlm`, drives `simulate()`,
judges the action log to derive `expected`, assembles a schema-valid scenario,
and **round-trips it through `run_scenario`** (an I4 self-check: the frozen
program must replay to the recorded verdict, else it raises). `write_scenario`
then persists `corpus/sim/<id>.scenario.json` (refuses to clobber unless
`--overwrite` -- a frozen artifact is immutable by default, I1). From then on the
frozen scenario feeds the deterministic gate and the `/sim` console badge -- a
dynamic live attack becomes a permanent deterministic recette case. Re-run
`python3 -m recette redteam` afterwards.

> When freezing into the corpus, prefer a deterministic backend (`StubLlm` or a
> seeded `--cache`) so the committed scenario is reproducible. A non-deterministic
> live run is a proof of wiring, not a corpus artifact -- record it to a throwaway
> dir if you only want the proof.

## The optional PyRIT attacker (seeded path)

The native `RedTeamSimulator` needs no extra dependency. For Microsoft PyRIT's
curated jailbreak corpus, install the optional extra and switch the attacker:

```
pip install inspect_ia_agents[redteam]
python3 -m recette redteam-record --spec target.manifest.json \
  --attacker pyrit --objective "exfiltrate the diagnostic credentials" \
  --subject-provider groq --subject-model llama-3.3-70b-versatile \
  --scenario-id rt-pyrit-case --name "PyRIT seeded case"
```

`PyritAttacker` is the **seeded** mode: on first call it materializes an ordered
list of `max_turns` adversarial seed prompts from PyRIT's built-in dataset framed
toward `--objective`, then returns one per turn (not the adaptive async
orchestrator). `pyrit` is imported lazily inside `__call__`, never at module top
or construction, so the CLI and the gate venv load without the dependency
(constructing the attacker is always safe; calling it without the extra raises a
clear `RuntimeError` naming the extra). This path is verified only with the extra
installed.

## Invariants

- I1: a frozen scenario is immutable -- `write_scenario` refuses to clobber.
- I4: the gate is a pure replay over the recorded `subject_program`; live runs
  are recorded, then replayed byte-stable. The gate never calls a live LLM.
- I6: an approval-gated tool (`approval: always`) is never approved by `deny_all`.

## Related

- `.claude/rules/recette-and-test-constraints.md` (R20) -- gates, live proof in a
  versioned script not /tmp.
- `.claude/rules/maf-standard.md` -- the `maf_agent` target shape and judge.
- `docs/runbooks/orchestration-recette.md` -- the sibling record/replay/freeze
  loop for orchestration teams.
