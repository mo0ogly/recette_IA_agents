# Migration provenance -- what was taken from the source repos (verifiable)

> Proof that the capture layer adapts REAL code from the upstream repos (read via
> `gh api`), not invented. Each row cites a verifiable upstream symbol/path and
> the local code that adapts it. Honest distinction: PATTERN + FIELD SET are
> reused; the LAYER and STORE are re-homed into this project's seams (the upstream
> code does not drop in unchanged because it targets a different layer/runtime).
> Licenses: agentwatch Apache-2.0, agenttrace MIT (see NOTICE).

## cyberark/agentwatch (Apache-2.0) -- the hook MECHANISM

Source read: `src/agentwatch/hooks/base.py`, `src/agentwatch/llm/models.py`,
`src/agentwatch/hooks/http/*`.

| Upstream (real symbol) | Local adaptation | Reuse vs adapt |
|------------------------|------------------|----------------|
| `BaseHook.apply_hook()` / `should_intercept(*args)` (`hooks/base.py`) | `CapturingLlm` wraps an `LlmBackend`; the wrap IS the applied hook, `should_intercept` is implicit (every `decide()`) | PATTERN reused |
| `HookCallbackProto.on_hook_callback(hook, obj)` (`hooks/base.py`) | `CapturingLlm(sink=...)` -- the sink callback receiving each `LlmCallTrace` | PATTERN reused |
| `ToolUse` / `Message` / `Tool` LLM wire models (`llm/models.py`) | `LlmCallTrace.intent = {tool}:{resource}` captured from the decision's tool call | DATA SHAPE reused |
| `hooks/http/httpcore_hook.py` (interception at the **httpcore/HTTP** layer) | NOT used at httpcore: we hook the `LlmBackend.decide()` seam (we own it). In our stack, HTTP-transport interception IS the wire surface (eBPF `discoveryprobe` / `ProxyTrace`) | LAYER ADAPTED (deliberate) |

Honest statement: agentwatch intercepts the HTTP transport (httpcore) and parses
provider wire formats. We do not replicate httpcore hooking in-process; we wrap
the higher-level `LlmBackend` interface. The MECHANISM (hook object + callback
sink + capture tool-call intent) is faithfully reused; the LAYER differs by
design (sync-first to our existing `CachingLlm` idiom).

## tensorstax/agenttrace (MIT) -- the trace SCHEMA

Source read: `src/agenttrace/agenttrace.py`.

| Upstream (real symbol) | Local adaptation | Reuse vs adapt |
|------------------------|------------------|----------------|
| `TraceManager._log_trace_end(func_name, session_id, duration_ms, success)` | `LlmCallTrace{intent (~func_name), agent_id/run_id (~session_id), latency_ms (~duration_ms), error (~not success)}` | FIELD SET reused |
| `traces` table columns `id, trace_type, timestamp, ...` (`CREATE TABLE traces`) | `LlmCallTrace{seq/event_id, kind (~trace_type)}` + ops fields | FIELD SET reused |
| `TraceManager` SQLite `traces.db` + `save_traces` | NOT used: re-homed into `CaptureStore` (bounded ring) + the audit log (I1 truth) -- no parallel SQLite | STORE RE-HOMED |
| `@tracer.trace()` decorator | NOT used: the wrap is the `LlmBackend` wrapper, not a per-function decorator | MECHANISM ADAPTED |

Honest statement: agenttrace persists to its own SQLite and decorates functions.
We reuse its enriched per-call FIELD SET (intent + duration/latency + success/error
+ session/run) but store into this project's existing capture/audit seams, not a
parallel database.

## Verify it yourself

```
gh api repos/cyberark/agentwatch/contents/src/agentwatch/hooks/base.py --jq '.content' | base64 -d
gh api repos/tensorstax/agenttrace/contents/src/agenttrace/agenttrace.py --jq '.content' | base64 -d
```
Compare with `recette/capture/capturing_llm.py` and `recette/capture/llm_trace.py`.

## Rust parts (different skill)

The native eBPF wire surface (`discoveryprobe/`) is Rust, built under the
`rust-best-practices` skill (idiomatic borrowing, clippy `-D warnings`, fmt). It
is NOT a migration of these Python repos -- it is the no-cooperation kernel
backstop that complements the Python hook. See
`docs/plans/2026-06-16-discoveryprobe-ebpf-reference-probe-design.md`.
