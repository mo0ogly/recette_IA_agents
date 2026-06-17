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
  **throwaway view** -- the durable truth stays in the append-only audit log (I1).
- The console (`/proxy`) renders traces read-only in Monaco: a list on the left,
  a JSON inspector / JSONL stream on the right.

Determinism (I4): a trace carries no wall-clock value of its own. Ordering comes
from a monotone `seq`; `timestamp` is the event's already-captured logical clock.

## Enable it (parameterizable, R5)

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

## Wire interception overlay (mitmproxy) -- the network-level view

The `ProxyTrace` above is the **application-level** view (the agent's intent at
the `ExternalSystemProxy` boundary). The **wire overlay** adds the
**network-level** view: the bytes actually on the wire of the agent -> target
traffic, captured by a real interception proxy (**mitmproxy**) running as an
OPTIONAL Docker overlay. Two altitudes of the same I5 side effect.

It is **off by default** and an ADD-ON, never a replacement: the deterministic
recette never routes through it (I4 unchanged), the home-grown `TracingProxy`
stays the default.

### In the UX

The `/proxy` page has a source toggle: **app traces** (the `ProxyTrace` list) and
**wire (mitmproxy)** (`WirePanel`: status, flow list, request/response detail,
clear). When the overlay is not configured the panel shows how to enable it
rather than an empty list.

### Choosing the transport route (proxy selector)

A shared **`ProxySelector`** lets an operator pick the transport agent side
effects take -- **Direct (no proxy)** or **Wire (mitmproxy)** -- from the
windows that have a network console: the `/proxy` wire panel and the per-run
**Network logs** (cockpit `AgentRunModal`). It is backed by `GET`/`POST
/proxy/route`; the selection is held server-side (so every console reflects the
same active route) and applies to runs started afterwards. Transport only: the
route never changes the decision (allow/deny/escalate) or the recorded action
log (I4). Backed by `recette/platform/proxy/route.py` (`ProxyRouteRegistry`);
the run routers pass the active route's `wire_proxy_url` into the runner. The
initial route is `wire` when `INSPECT_IA_AGENTS_WIRE_PROXY` is set, else `direct`.

The console **AI backends** form (Agents tab) also carries a **LiteLLM gateway
(local)** preset that one-clicks an `openai_compat` backend pointing at the
LiteLLM overlay (`http://127.0.0.1:4000`); see `llm-gateway-litellm.md`.

### Architecture

```
agent --(HTTP proxy)--> [mitmproxy container] --> lab / real system
                             | addon POSTs each flow
                             v
                     API POST /proxy/wire --> WireFlowRecorder (bounded ring, I1)
                             ^
                Proxy page <--GET /proxy/wire (status + flows)
```

- `recette/platform/proxy/wire.py` -- `WireFlow` + `WireFlowRecorder` (mirrors
  the trace ring: bounded, monotone `seq`, throwaway) + pure `normalize_flow`.
- `scripts/mitm_wire_addon.py` -- mitmdump addon: normalizes each flow and POSTs
  it to the API ingest (fail-safe, never alters traffic).
- Endpoints: `POST /proxy/wire` (ingest), `GET /proxy/wire` (+ `tail`, `run_id`),
  `DELETE /proxy/wire`, `GET /proxy/wire/status`.

### Bring it up (R19, never hand-launch)

```
./recette.sh wire up
export INSPECT_IA_AGENTS_WIRE_PROXY=http://127.0.0.1:8083
./recette.sh api restart
```

The agent's lab-mode side effects (mock_local / declared_url) then route through
mitmproxy and show up in the wire panel. `./recette.sh wire down|status|logs`
manage the container; `wire ca` prints the CA path.

### HTTPS to real systems (real_saas)

mitmproxy decrypts HTTPS only if the client trusts its CA:

```
export INSPECT_IA_AGENTS_WIRE_CA="$(./recette.sh wire ca)"
# SDK forges (PyGithub / python-gitlab) honour the standard env instead:
export HTTPS_PROXY=http://127.0.0.1:8083 REQUESTS_CA_BUNDLE="$(./recette.sh wire ca)"
./recette.sh api restart
```

- `StdlibHttpClient` gained a `ca_bundle` seam; `RealSlackProxy` (Slack over
  StdlibHttpClient) routes through the overlay + CA from `INSPECT_IA_AGENTS_WIRE_*`.
- TLS verification stays ON -- the CA is **added**, never disabled.

### Determinism (I4)

The overlay is OFF in every deterministic recette and never sits in the
decision/replay path. A `WireFlow` carries no wall-clock value; ordering is the
recorder's monotone `seq`, exactly like `ProxyTrace`.

### Live proof

`scripts/smoke_wire.py` -- self-skips without Docker; otherwise brings the
overlay up, drives a request through it to the lab, and asserts the flow reaches
`GET /proxy/wire`.

### Wire tests

| Test | Proves |
|------|--------|
| `tests/test_wire_proxy.py` | WireFlow normalize/clamp, bounded ring, monotone seq, immutability |
| `tests/test_api_wire.py` | `/proxy/wire*` endpoints; ingest/list/clear/status; tail; run_id; 422 |

### Wire-vs-audit reconciliation -- detecting an unmediated (ghost-agent) path

Holding the two altitudes side by side turns the overlay into a detector for the
"ghost agent" / shadow-AI threat: an unregistered agent that talks straight to an
external system via native code, bypassing the `ExternalSystemProxy` (and thus the
Control Plane). Such a call produces a **network side effect with no audit event**.

The two views make it visible:

- the **audit chain** (append-only log, fed by the mediated `ProxyTrace`, I1/I5)
  is what went *through* the gateway;
- the **mitmproxy wire** is what was actually *on the network*.

So every flow seen on the wire should have a matching mediated event in the audit
log. A wire flow with **no audit counterpart** (a non-mediated target within its
run) is an **unmediated path** -- the loophole -- and is the signal to raise to the
Control Plane.

Status (implemented, allowlist + run-scoped join): `recette/platform/proxy/reconcile.py`
joins the wire view (`WireFlow`) with the audit view (`ProxyTrace`) by `run_id`
(`reconcile_run`); a flow to a non-mediated target (e.g. the `shadow-db-sink`
honeypot on `:9113`) is flagged as a bypass. Surfaced at `GET /proxy/reconcile` and
in the console (Proxy page, "reconciliation" tab). Proven end to end by the live
smoke `scripts/smoke_reconcile.py` (mitmproxy overlay up -> ghost probe writes
directly to `:9113` -> reconcile reports `ok:false` with the `:9113` bypass) and by
the deterministic unit/contract suites (`tests/test_reconcile.py`,
`test_api_reconcile.py`, `test_ghost_probe.py`, `ReconcilePanel.contract.test.tsx`).
A per-flow `side_effect_hash` join (ghost via an *allowlisted* target) is phase 3.
This stays a recette LAB: it *observes* the unmediated path, it does not *enforce* a
network block. Hard-blocking the direct outbound path (pod network isolation, plus
the boot-time identity handshake of I3) is the platform's job, not the simulation's.
The lab prepares and scores; enforcement is a separate layer.
| `tests/test_wire_routing.py` | proxy_url + ca_bundle seam; resolve_proxy threading; Slack wire env |
| `tests/test_mitm_addon.py` | addon flow normalization + fail-safe guards (no mitmproxy runtime) |
| `console/src/pages/proxy/WirePanel.contract.test.tsx` | R16 panel contract (real fixture, enabled/disabled) |
