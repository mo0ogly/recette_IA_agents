# Lane B agent -- specification (what a live LLM agent must do)

> Companion to the two-lane model (MASTER plan section 0bis). Lane A = deterministic
> ground-truth subjects (already built). Lane B = live, LLM-driven agents for realism and
> the console (Track U). This file defines what a Lane B agent IS and DOES, before any code.

## 1. Why Lane B exists

The discovery/identification tools are validated by Lane A (deterministic, measurable).
Lane B does NOT replace that. It exists to:

- make the corpus "as real as possible" -- a genuine LLM deciding and acting, not a script;
- power the console (Track U): launch an agent, watch it think and act live, debug it;
- generate NEW realistic runs that, once recorded, can be FROZEN into Lane A goldens.

Lane B output is **never** trusted as ground-truth while live (an LLM is non-deterministic).
It becomes trustworthy only after recording (section 6).

## 2. Definition

A **Lane B agent** is a real agent process where an **LLM decides the next action** inside a
bounded capability set, acting on a target system through a mediated proxy, with **every step
recorded** so the run is replayable afterward.

It is characterised by the same four things as any AgentRail agent:
- **identity** (`agent_id`, principal, auth_method) -- I3;
- **capability_scope** -- the tools it is allowed to call;
- **actions** -- real tool calls against a `target_system` (github/gitlab/...);
- **behavior** -- what its role is supposed to achieve (the goal it is given).

## 3. What it DOES (the loop, concretely)

```
inputs: manifest (identity + capability_scope + goal), forge (lab|real),
        llm backend, recorder
state:  history = []
loop (until final answer or max_steps):
  1. prompt = system(role, goal, allowed tools = capability_scope) + history
  2. step  = llm.decide(prompt)            # -> a tool call, or a final answer
  3. if tool call:
       a. tool in capability_scope?         # correct agent: always; overreach: not
       b. result, side_effect_hash = forge.execute(tool, args)   # mediated (I5)
       c. event = normalize(step -> AgentAction)  # canonical model, appended to log
       d. recorder.capture(prompt, model, raw_response, tool_call, result, event)
       e. history += (tool_call, result)
  4. else: stop
output: ordered AgentAction log  (same shape as a Lane A scenario)
        + full recording (replayable)
```

Key point: the **output is the same shape as Lane A** -- an ordered list of
`AgentAction` (recette/events.py). So discovery, identification, the scorecards, and the
console all consume Lane A and Lane B identically.

## 4. Anatomy (reuse what exists)

| Part | What | Reuse |
|------|------|-------|
| Identity + scope + goal | a manifest (extends the agent-manifest schema with a `goal`) | `corpus/schemas/agent-manifest.schema.json` |
| Tools | a registry mapping canonical actions -> forge calls; the agent only sees tools in its `capability_scope` | `recette/events.py` ActionType, `recette/forge.py` |
| Proxy / side effects | `LabForge` (simulated, default) or `RealForge` (real SDK, opt-in) | `recette/forge.py` (I5 mediation, `side_effect_hash`) |
| LLM backend | a `LlmBackend` protocol: `LiveLlm` (real API), `ReplayLlm` (recorded), `StubLlm` (scripted, offline tests) | NEW (`recette/llm.py`) |
| Recorder | writes a run recording (JSONL): per step model, prompt, response, tool call, result, AgentAction, hashes | NEW (`recette/recording.py`) |

## 5. Lab vs real (default: lab)

- **Lab mode (default).** `LabForge` -- zero real side effect, no real token. The LLM may be
  `LiveLlm` (real reasoning, simulated actions) OR `StubLlm`/`ReplayLlm` (fully offline).
  This is the safe default and what the console demos.
- **Real mode (explicit opt-in).** `RealForge` against **dedicated test orgs/repos only**,
  real tokens from env (R8). Never a production repo. Guarded the same way as the publisher
  (dry-run-ish: explicit `--real` flag + a test-org allowlist).

Mode is carried by the manifest (`runtime.lab_mode` / `runtime.real_mode`), as Lane A.

## 6. Recording & replay -- how non-determinism is captured (I4)

An LLM run is non-deterministic. We do NOT pretend otherwise; we **capture** it:

- The recorder writes, per step: the model id, the exact prompt, the raw response, the tool
  call, the tool result, the resulting `AgentAction`, and a `side_effect_hash`.
- **Replay** feeds the recording to a `ReplayLlm` that returns the recorded responses in
  order -- no API call, no cost, deterministic. Replaying a recording reproduces the exact
  `AgentAction` log. This is the I4 "capture the non-determinism as an input" rule applied
  to the LLM itself.
- A recording is therefore a self-contained, replayable artifact.

## 7. Lane B -> Lane A promotion (the bridge)

Because a recording replays deterministically, a vetted Lane B run can be **frozen** into a
Lane A fixture: take the recorded `AgentAction` log, save it as a `scenario.json` +
`ground-truth.json`, and it joins the measurable corpus. This is how live realism feeds the
ground-truth set without ever trusting a live LLM as truth.

## 8. Correct vs incorrect Lane B subjects

Like Lane A, Lane B can be correct or deliberately incorrect, to exercise identification:
- a **correct** agent only calls tools in its `capability_scope` and stays on-role;
- an **incorrect** agent is set up to break exactly one dimension -- e.g. given a tool
  outside its declared scope (`capability_overreach`), or a mismatched principal
  (`identity_mismatch`), or prompted toward off-role/spam behavior (`behavior_anomaly`).
  The break is in the SETUP, not in hoping the LLM misbehaves.

## 9. What Lane B is NOT

- NOT ground-truth while live (only after recording).
- NOT the platform: a Lane B agent is a SUBJECT the tools observe; it does not enforce the
  Control Plane. Its side effects are still mediated (I5) so the lab is side-effect-free.
- NOT required for discovery/identification validation -- that is Lane A's job. Lane B is
  realism + console + a source of new goldens.

## 10. Invariant mapping

- I3 identity: agent runs under a resolved principal; recorded.
- I4 determinism: live runs are non-deterministic but RECORDED; replay is deterministic.
- I5 mediated side-effects: all tool calls go through the forge proxy; `side_effect_hash`.
- I2/I6 (control-plane/approval): out of scope for the subject; the platform enforces these.

## 11. Decisions (resolved 2026-06-11)

1. **LLM backend** -- **multi-provider**. A `LlmBackend` protocol with provider adapters
   (Claude/Anthropic, OpenAI, ...) for live mode (keys via env, R8), plus offline
   `StubLlm` (scripted) and `ReplayLlm` (recorded) so tests + CI need no key and no cost.
2. **v1 action surface** -- **all surfaces** (github, gitlab, openapi, temporal, mcp). Needs
   a per-surface forge mapping canonical actions -> simulated (lab) / real calls.
3. **Promotion** -- **in v1**: a command that freezes a recorded run into a Lane A golden
   (`scenario.json` + `ground-truth.json`).
4. **Real mode** -- **in v1, opt-in**: `RealForge` guarded by an explicit `--real` flag + a
   test-org/endpoint allowlist; lab is still the default and the only thing CI runs.

## 12. Build decomposition (v1) -- DONE 2026-06-11

The Lane B engine is built, tested, and green in CI (128 tests, gates PASS). Live-LLM and
real-mode adapters are unit-tested with stubbed transports (no key, no network, no side
effect) -- like `http_adapter`.

- **LB1 LLM backend** [DONE] -- `recette/llm.py`: `LlmBackend` protocol; `StubLlm` +
  `ReplayLlm` (offline, deterministic); `AnthropicLlm`/`OpenAiLlm` over the stdlib client
  (zero SDK dep), stub-tested; `build_llm` factory. Keys via env.
- **LB2 tool registry** [DONE] -- `recette/tools.py`: canonical actions as tools;
  `execute_tool` runs the chosen tool through the (surface-agnostic) forge -> `AgentAction`.
- **LB3 agent loop + recorder** [DONE] -- `recette/lane_b.py` decide->act loop;
  `recette/recording.py` captures every step (no wall-clock, save/load).
- **LB4 replay** [DONE] -- `ReplayLlm` reproduces an identical `AgentAction` log.
- **LB5 promotion** [DONE] -- `recette/promote.py` `freeze_recording` -> Lane A
  manifest+scenario+ground-truth; round-trips green through `run_recette`.
- **LB6 real mode** [DONE] -- `recette/realmode.py` `AllowlistForge` + `build_real_forge`
  (token + allowlist via env, fail-fast); `agent run --real`. Lab stays CI default.
- **LB7 CLI** [DONE] -- `recette agent run|replay|freeze`.

This engine is the foundation the console (Track U U2-U4) drives. Remaining for Lane B:
concrete per-action SDK dispatch in `RealForge` is a deployment concern (documented there);
everything the recette needs is in place.
