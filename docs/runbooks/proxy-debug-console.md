# Runbook -- Proxy debug console (side-effect tracing, I5)

The side-effect proxy is the only path from agent logic to an external system
(invariant I5). This runbook covers the **debug tracing** layer that records each
proxy `execute()` and the **Monaco console** that displays it, plus the
**real_saas** wiring that lets a run execute through an allowlisted real forge.

## What it does

- A `TracingProxy` decorates ANY `ExternalSystemProxy` (lab or real) and records
  one `ProxyTrace` per `execute()`: the request intent (event id, agent, action,
  target system, resource, payload) and the outcome (`ok`, status code,
  `side_effect_hash`, error).
- Traces live in a bounded in-memory ring (`RingTraceRecorder`). The ring is a
  **jettable view** -- the durable truth stays in the append-only audit log (I1).
- The console (`/proxy`) renders traces read-only in Monaco: a list on the left,
  a JSON inspector / JSONL stream on the right.

Determinism (I4): a trace carries no wall-clock value of its own. Ordering comes
from a monotone `seq`; `timestamp` is the event's already-captured logical clock.

## Enable it (parametrable, R5)

Tracing is off by default (zero overhead). Turn it on with an environment
variable read at app startup:

```
INSPECT_IA_AGENTS_PROXY_DEBUG=on
```

Truthy values: `1`, `true`, `yes`, `on` (case-insensitive). Anything else is off.
When off, the proxy executes normally and **nothing is recorded** -- the console
shows a banner saying so rather than an empty list that looks like steady state.

## What gets traced

Two paths feed the same shared recorder:

1. **Gateway path** -- `POST /actions/execute` (and approval-driven execution).
   The gateway's side-effect proxy is wrapped at app construction.
2. **Lane B agent path** -- a registered agent bound to a `server` entry runs its
   tool calls through `ProxyForge`; that resolved proxy is wrapped too. So a real
   agent's side effects show up in the console.

An agent with **no** `server` binding uses the in-memory `LabForge`, which
produces no external side effect and is therefore not traced.

## API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/proxy/debug` | `{debug_enabled, trace_count}` |
| GET | `/proxy/traces?tail=N` | recorded traces (oldest first; `tail` keeps last N) |
| DELETE | `/proxy/traces` | discard the buffer (the audit log is untouched, I1) |

Example:

```
curl -s http://127.0.0.1:8080/proxy/debug
curl -s "http://127.0.0.1:8080/proxy/traces?tail=50"
curl -s -X DELETE http://127.0.0.1:8080/proxy/traces
```

## real_saas wiring

The proxy `router` (`resolve_proxy`) is pure: it reads no env and holds no
credentials, so a `real_saas` server entry raised `ValueError` by default. It now
accepts an injected `real_proxy_factory`:

- `recette/platform/proxy/real_proxy.py` provides `RealForgeProxy` (adapts a forge
  to `ExternalSystemProxy.execute`) and `build_real_proxy_factory(*, enable_writes=False)`.
- The factory builds an **allowlisted** real forge from the environment
  (`recette.realmode.build_real_forge`): token via `INSPECT_IA_AGENTS_<SYSTEM>_TOKEN`,
  allowlist via `INSPECT_IA_AGENTS_REAL_ALLOWLIST`, writes disabled unless explicitly
  enabled (R8).

Fail-safe (failure-modes): an allowlist rejection, a blocked write, a missing SDK
or any forge error is mapped to `ExecutionResult(ok=False, ...)` -- the proxy never
raises through the gateway and never falls back to the wrong target (I5).

Wire it at an impure call-site:

```python
from recette.platform.proxy.router import resolve_proxy
from recette.platform.proxy.real_proxy import build_real_proxy_factory

proxy = resolve_proxy(
    agent, servers, default_proxy,
    real_proxy_factory=build_real_proxy_factory(enable_writes=False),
)
```

Lab stays the default everywhere; real mode is opt-in and only ever touches
allowlisted test orgs.

## Tests

| Test | Proves |
|------|--------|
| `tests/test_proxy_tracing.py` | decorator records/returns verbatim, fail-safe, bounded ring, env toggle |
| `tests/test_real_proxy.py` | success -> hash; allowlist/write/forge errors -> fail-safe |
| `tests/test_proxy_router.py` | real_saas uses the injected factory; no factory -> error (backward compat) |
| `tests/test_api_proxy_traces.py` | `/proxy/*` endpoints; debug on/off; tail; clear |
| `tests/test_api_proxy_traces_lane_b.py` | a REAL Lane B agent's side effects are traced (debug on) / not (off) |
| `console/src/pages/proxy/*.test.{ts,tsx}` | model helpers + R16 page contract against a real fixture |

## Failure modes

- Recording exception -> swallowed; `execute()` always returns the wrapped result
  (observability must never break the I5 path).
- Debug off -> no recording, no console data, banner shown.
- Buffer full -> oldest traces drop (bounded ring); `seq` stays monotone; the
  audit log remains complete.
