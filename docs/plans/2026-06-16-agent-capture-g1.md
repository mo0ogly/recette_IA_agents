# Agent Capture G1 (in-process hook) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use the project APEX loop (`/apex`) or
> superpowers:executing-plans to implement this plan task-by-task. Python build
> pipeline per `.claude/skills/apex/_shared/references/build-pipeline-python.md`.

**Goal:** Capture an agent's in-process LLM/tool decisions (the hook surface),
re-homed into the existing planes: feed the real `hook_sdk`/`hook_mcp`
`SurfaceRecording` (detection) AND an enriched LLM-call trace (tokens/latency/
error), without a parallel silo.

**Architecture:** Migrate agentwatch's interception MECHANISM, adapted to this
codebase's existing wrapper idiom: a `CapturingLlm(inner)` that wraps any
`LlmBackend` (exactly like the existing `CachingLlm` in `recette/llm_cache.py`),
records each `decide()` as an `LlmCallTrace`, and emits a `SurfaceObservation`
on the `hook_sdk` surface. Detection stays deterministic (I4); wall-clock latency
is operational metadata, off the judge path (`maf-standard.md`). eBPF
(`discoveryprobe`) remains the no-cooperation backstop for ghosts.

**Tech Stack:** Python stdlib + `recette/llm.py` (LlmBackend, LlmDecision),
`recette/surface/` (ObservationSurface, SurfaceObservation, recording.py),
`recette/events.py` (LogicalClock), unittest. Migrated fields from
tensorstax/agenttrace (MIT); mechanism from cyberark/agentwatch (Apache-2.0),
attribution preserved.

**Determinism note:** tokens/model/intent are deterministic (read from
`LlmDecision.raw`/the decision). `latency_ms` and any timestamp are wall-clock =
operational only; they are excluded from the detection recording and any judged
hash.

---

## Attribution (do FIRST, Task 0)

### Task 0: NOTICE for migrated mechanism/schema

**Files:**
- Create: `recette/capture/__init__.py`
- Create: `NOTICE` (append a section if it exists)

**Step 1:** Create `recette/capture/__init__.py`:

```python
"""In-process agent capture (hook surface).

The interception mechanism is adapted from cyberark/agentwatch (Apache-2.0); the
enriched-trace field set is adapted from tensorstax/agenttrace (MIT). Both are
re-homed into this project's existing seams (the LlmBackend wrapper idiom, the
surface recording, the proxy trace recorder) rather than copied as a parallel
tool. See NOTICE and docs/plans/2026-06-16-agent-capture-multisurface-design.md.
"""
```

**Step 2:** Create/append `NOTICE` at repo root with the two attributions
(project name, the two source repos, their licenses, "mechanism/schema adapted").

**Step 3: Commit**

```bash
git add recette/capture/__init__.py NOTICE
git commit -m "chore(capture): scaffold capture package + upstream attribution (agentwatch/agenttrace)"
```

---

## Task 1: `LlmCallTrace` -- the enriched LLM-call record (schema migrated from agenttrace)

**Files:**
- Create: `recette/capture/llm_trace.py`
- Test: `tests/test_capture_llm_trace.py`

**Step 1: Write the failing test**

```python
from recette.capture.llm_trace import LlmCallTrace

def test_to_dict_round_trips_intent_and_ops_fields():
    t = LlmCallTrace(
        seq=1, event_id="EV1", agent_id="a1", model="llama-3.3-70b-versatile",
        kind="tool_call", tool_name="read_repo", resource="acme/x",
        prompt_tokens=120, completion_tokens=18, latency_ms=842, error=None,
    )
    d = t.to_dict()
    assert d["intent"] == "read_repo:acme/x"          # the hook key shape
    assert d["total_tokens"] == 138
    assert d["latency_ms"] == 842
```

**Step 2:** Run `python3 -m unittest tests.test_capture_llm_trace -v` -> FAIL (no module).

**Step 3: Implement** `recette/capture/llm_trace.py` -- a frozen dataclass with:
`seq:int, event_id:str, agent_id:str, model:str, kind:str,
tool_name:str|None, resource:str, prompt_tokens:int, completion_tokens:int,
latency_ms:int, error:str|None`. A `to_dict()` that adds derived
`intent = f"{tool_name}:{resource}"` (empty tool_name -> `":resource"`) and
`total_tokens`. `intent` MUST match `recette/surface/surfaces.py::_hook_key`
shape (`{action_type}:{resource}`) so the hook surface key lines up.

**Step 4:** Run the test -> PASS.

**Step 5: Commit**

```bash
git add recette/capture/llm_trace.py tests/test_capture_llm_trace.py
git commit -m "feat(capture): LlmCallTrace enriched record (intent + ops tokens/latency)"
```

---

## Task 2: usage extraction from `LlmDecision.raw` (provider-agnostic)

**Files:**
- Create: `recette/capture/usage.py`
- Test: `tests/test_capture_usage.py`

**Context:** Providers store the raw response on `LlmDecision.raw`. OpenAI/Groq/
others put token counts under `raw["usage"]` with `prompt_tokens` /
`completion_tokens`; Anthropic uses `usage.input_tokens` / `output_tokens`.

**Step 1: Write the failing test**

```python
from recette.capture.usage import extract_usage

def test_openai_style_usage():
    assert extract_usage({"usage": {"prompt_tokens": 10, "completion_tokens": 3}}) == (10, 3)

def test_anthropic_style_usage():
    assert extract_usage({"usage": {"input_tokens": 7, "output_tokens": 2}}) == (7, 2)

def test_missing_usage_is_zero():
    assert extract_usage({}) == (0, 0)
```

**Step 2:** Run -> FAIL.

**Step 3: Implement** `extract_usage(raw: dict) -> tuple[int, int]` returning
`(prompt_tokens, completion_tokens)`, tolerant of both shapes and missing keys
(default 0). No exceptions on malformed input (fail-safe).

**Step 4:** Run -> PASS.

**Step 5: Commit**

```bash
git add recette/capture/usage.py tests/test_capture_usage.py
git commit -m "feat(capture): provider-agnostic token usage extraction"
```

---

## Task 3: `CapturingLlm` wrapper (the interception, mirrors CachingLlm)

**Files:**
- Read first: `recette/llm_cache.py` (the existing wrapper idiom to mirror)
- Create: `recette/capture/capturing_llm.py`
- Test: `tests/test_capturing_llm.py`

**Context:** `LlmBackend` is a Protocol with
`decide(*, system, history, tools) -> LlmDecision`. The wrapper holds an inner
backend, an `event_id` source (sequence, NOT a clock -- I4), and an optional
sink list it appends `LlmCallTrace` to. It MUST be fail-safe: a sink error never
breaks `decide` (the agent keeps running -- observation never blocks execution).

**Step 1: Write the failing test**

```python
from recette.capture.capturing_llm import CapturingLlm
from recette.llm import StubLlm, LlmDecision

def test_records_one_trace_per_decision_with_intent():
    inner = StubLlm([LlmDecision(kind="tool_call", tool_name="read_repo",
                                 tool_args={"resource": "acme/x"},
                                 raw={"usage": {"prompt_tokens": 5, "completion_tokens": 1}})])
    traces = []
    llm = CapturingLlm(inner, agent_id="a1", model="m", sink=traces.append)
    llm.decide(system="s", history=[], tools=[])
    assert len(traces) == 1
    assert traces[0].tool_name == "read_repo"
    assert traces[0].resource == "acme/x"
    assert traces[0].prompt_tokens == 5

def test_sink_failure_does_not_break_decide():
    inner = StubLlm([LlmDecision(kind="final", text="done")])
    def boom(_): raise RuntimeError("sink down")
    llm = CapturingLlm(inner, agent_id="a1", model="m", sink=boom)
    # decide still returns the inner decision (fail-safe)
    assert llm.decide(system="s", history=[], tools=[]).kind == "final"
```

**Step 3: Implement** `CapturingLlm`:
- `__init__(self, inner, *, agent_id, model, sink=None)`; internal `_seq=0`.
- `decide(...)`: call `inner.decide(...)`; `_seq += 1`; build an `LlmCallTrace`
  (seq, event_id=`f"LC{self._seq:06d}"`, agent_id, model, kind=decision.kind,
  tool_name=decision.tool_name, resource=`decision.tool_args.get("resource","")`,
  tokens via `extract_usage(decision.raw)`, `latency_ms` measured around the
  inner call with `time.perf_counter` -- ops only, OK here because it never
  enters detection/judge, error=None); call `sink(trace)` inside try/except
  (swallow + ignore, fail-safe); return the original decision unchanged.
- `latency_ms` uses `perf_counter` (monotonic, wall-clock-ish) -- this is the one
  allowed wall-clock read because it is OPERATIONAL metadata never fed to the
  judge (document this in a comment, cite maf-standard.md).

**Step 4:** Run `python3 -m unittest tests.test_capturing_llm -v` -> PASS.

**Step 5: Commit**

```bash
git add recette/capture/capturing_llm.py tests/test_capturing_llm.py
git commit -m "feat(capture): CapturingLlm wrapper records LlmCallTrace, fail-safe"
```

---

## Task 4: bridge captured intents -> `hook_sdk` SurfaceRecording

**Files:**
- Read first: `recette/surface/surfaces.py`, `recette/surface/recording.py`
- Create: `recette/capture/surface_bridge.py`
- Test: `tests/test_capture_surface_bridge.py`

**Context:** `ObservationSurface.HOOK_SDK = "hook_sdk"`. The detection key for a
hook surface is `{action_type}:{resource}` (`surfaces.py::_hook_key`). The bridge
turns a list of `LlmCallTrace` (one agent) into a `CaptureRecording` with the
tool-call intents on `hook_sdk` -- so the SAME judge/scorecard
(`recette/surface/recording.py`) scores a hook capture exactly like an eBPF one.

**Step 1: Write the failing test**

```python
from recette.capture.llm_trace import LlmCallTrace
from recette.capture.surface_bridge import recording_from_traces
from recette.surface.surfaces import ObservationSurface

def test_tool_calls_become_hook_sdk_visible():
    traces = [LlmCallTrace(seq=1, event_id="LC1", agent_id="a1", model="m",
              kind="tool_call", tool_name="read_repo", resource="acme/x",
              prompt_tokens=0, completion_tokens=0, latency_ms=9, error=None)]
    rec = recording_from_traces("a1", traces)
    assert rec.surfaces[ObservationSurface.HOOK_SDK] == ("read_repo:acme/x",)

def test_final_only_run_is_seen_nowhere_on_hook():
    traces = [LlmCallTrace(seq=1, event_id="LC1", agent_id="ghost", model="m",
              kind="final", tool_name=None, resource="", prompt_tokens=0,
              completion_tokens=0, latency_ms=1, error=None)]
    rec = recording_from_traces("ghost", traces)
    assert ObservationSurface.HOOK_SDK not in rec.surfaces  # nothing observable
```

**Step 3: Implement** `recording_from_traces(agent_id, traces) ->
CaptureRecording` (the Python `recette/surface/recording.py::CaptureRecording`):
only `kind == "tool_call"` traces are observable on `hook_sdk` (a pure thought/
final reveals no action); key = `f"{tool_name}:{resource}"`; sorted + deduped via
the existing `CaptureRecording.surfaces` shape. NO latency/tokens in the
recording (detection is deterministic; ops metrics live only on the trace).

**Step 4:** Run -> PASS.

**Step 5: Commit**

```bash
git add recette/capture/surface_bridge.py tests/test_capture_surface_bridge.py
git commit -m "feat(capture): bridge captured tool-calls to the hook_sdk surface (deterministic)"
```

---

## Task 5: determinism / replay test (I4) + ghost cross-surface

**Files:**
- Test: `tests/test_capture_determinism.py`

**Step 1: Write the failing test** (two cases):

```python
# (a) the hook recording is byte-stable across two identical captured runs
def test_hook_recording_is_byte_stable():
    traces = _capture_run()        # helper: run CapturingLlm over a fixed StubLlm script
    a = recording_from_traces("a1", traces)
    b = recording_from_traces("a1", _capture_run())
    assert a.surfaces == b.surfaces

# (b) ghost: an agent observed ONLY on ebpf_wire (no hook tool-calls) is detected
#     on eBPF and blind on hook -> score_recording marks it caught, hook-blind
def test_ghost_is_caught_on_ebpf_blind_on_hook():
    from recette.surface.recording import score_recording
    import json
    rec = {"recordings": [
        {"agent_id": "ghost", "surfaces": {"ebpf_wire": ["exec:ghost:7"]}},  # eBPF sees
    ], "status": "ok"}
    card = score_recording(json.dumps(rec))
    assert card.ok                                   # caught somewhere (eBPF)
    assert card.detected_per_surface.get("hook_sdk", 0) == 0   # blind on hook
```

**Step 3:** No new impl -- this test asserts properties of Tasks 3-4 + the
existing `score_recording`. Add the `_capture_run` helper in the test.

**Step 4:** Run -> PASS.

**Step 5: Commit**

```bash
git add tests/test_capture_determinism.py
git commit -m "test(capture): hook recording byte-stable (I4) + ghost caught on eBPF, blind on hook"
```

---

## Task 6: wire `CapturingLlm` into the Lane B runner (opt-in, sync-first)

**Files:**
- Read first: `recette/api/runners.py` (`make_lane_b_runner`)
- Modify: `recette/api/runners.py`
- Test: `tests/test_runners_capture.py`

**Step 1: Write the failing test:** building a lane_b runner with capture enabled
collects `LlmCallTrace`s for the run, and the run's actions still execute
unchanged (capture is transparent).

**Step 3: Implement:** wrap the runner's `llm` in `CapturingLlm` when a capture
sink is provided (a new optional param, default None = no capture, zero behavior
change). The wrap is the ONLY change -- the decide->act loop is untouched.

**Step 4:** Run -> PASS. Also run the full lane_b suite to prove no regression:
`python3 -m unittest tests.test_api_lane_b_run tests.test_runners -v`.

**Step 5: Commit**

```bash
git add recette/api/runners.py tests/test_runners_capture.py
git commit -m "feat(capture): opt-in CapturingLlm wrap in the lane_b runner (transparent)"
```

---

## Task 7: API -- expose captured LLM traces

**Files:**
- Read first: `recette/api/routers/proxy.py` (the existing trace endpoint shape)
- Create: `recette/api/routers/capture.py` (or extend `probe.py`)
- Modify: `recette/api/app.py` (include the router)
- Test: `tests/test_api_capture.py`

**Step 1: Write the failing test:** `GET /capture/llm-traces?run_id=...` returns
the captured `LlmCallTrace.to_dict()` list for a run (empty list when none).

**Step 3: Implement** a small router backed by an in-memory per-run sink
(mirror `RingTraceRecorder`'s bounded ring). Raw JSON (no envelope, like the
other routers). Fail-safe: unknown run -> empty list, never 500.

**Step 4:** Run with the venv (`.venv/bin/python -m unittest tests.test_api_capture`).

**Step 5: Commit.**

---

## Task 8: UX -- show hook LLM traces (R16 contract gate)

**Files:**
- Read first: `console/src/pages/proxy/proxyTraceModel.ts`, `WirePanel.tsx`
- Create: `console/src/pages/probe/__fixtures__/llm-traces.fixture.json` (REAL
  payload captured from Task 7)
- Modify: `console/src/pages/probe/index.tsx` (a "Trace LLM" panel) + client.ts
- Test: `console/src/pages/probe/llmTraces.test.tsx`

**Step 1:** Capture the real payload from `GET /capture/llm-traces` -> fixture.

**Step 2:** Write the render-and-assert test (R16): render the panel with the
fixture, assert a row shows `intent` + `total_tokens` + `latency_ms`, and that an
error trace renders its error.

**Step 3:** Implement the typed client fn + the panel (theme tokens only, lux,
mirror `WirePanel` style). Service returns the typed list.

**Step 4:** `node node_modules/.bin/tsc --noEmit` clean +
`node node_modules/.bin/vitest run src/pages/probe` green +
`node node_modules/.bin/vite build` clean.

**Step 5: Commit.**

---

## Task 9: coverage guard + docs + live proof

**Files:**
- Modify: `tests/test_coverage_guard.py` (assert the real `hook_sdk` capture path
  is exercised, not a silent gap)
- Modify: `docs/runbooks/` (a short capture runbook) + the design doc status
- Modify: `scripts/run_discovery_loop_live_groq.py` OR a new
  `scripts/run_capture_live_groq.py` -- run a REAL Groq agent THROUGH
  `CapturingLlm`, print the captured traces (live proof, R14), record a replay
  fixture for the deterministic test.

**Step 1-4:** Add the guard assertion; write the runbook; run the live capture
once (key from `.env`, R18) to prove real tokens/latency are captured; freeze the
recording.

**Step 5: Commit + push.**

---

## Gates before "done" (R20)

| Gate | Command |
|------|---------|
| Python lint/format/type/security | `make gates` |
| Python suite | `./recette.sh test` |
| Recette + coverage guard | `make recette` |
| Console build + tests | `./recette.sh console-build` + `./recette.sh console-test` |
| Live wiring | `./recette.sh smoke` (+ the live Groq capture proof) |

## Out of scope (G1) -- deferred to G2/G3

- Full cost model (pricing tables) -> G2.
- Monkeypatching ARBITRARY external frameworks (LangChain/LangGraph/Autogen) ->
  G3 (G1 wraps OUR `LlmBackend`, which is the sync-first seam).
- MCP-over-HTTP/SSE interception -> G2 (G1 covers the in-process `decide()` hook;
  `hook_mcp` lands when the MCP tool-call path is wrapped the same way).
