# Private DNS resolver for lab servers -- design

Date: 2026-06-15
Status: APPROVED (design phase)
Planes touched: Data Plane (proxy egress), Audit Plane (resolution_denied event)
Invariants in scope: I2 (mediation), I4 (deterministic resolution), I5 (mediated side-effects)

## Objective

Give the lab servers stable internal names instead of raw `127.0.0.1:port`,
with two operator-facing goals, both fully configurable from the console UX:

- **A -- trace realism / legibility.** An agent's `ProxyTrace.target` reads
  `api.github.com` (or `github.lab.internal`) instead of `127.0.0.1:9101`, so a
  recette reader sees what the agent *meant* to reach, not a port number.
- **C -- containment.** The resolver is an allowlist gate: it resolves ONLY the
  declared names. An undeclared name is denied (fail-safe), audited as a
  `resolution_denied` event, and no network call is made -- an exfil signal.

Distributed service discovery (Phase 2 / "B") is explicitly OUT of scope for
this iteration; the same config table renders to a real resolver later when
hosts split (see "Phasing").

## Why this shape

Resolution is a PURE function of the committed server table (config), not a
runtime DNS lookup. Mono-host, there is no DNS server and no network I/O in the
resolve path -- so resolution stays byte-deterministic (I4) and adds zero
operational component (consistent with the phased minimal-ops ethos of the
event store). DNS here is defense-in-depth, NEVER a replacement for proxy
mediation: a resolved name still traverses Gateway + proxy (I2/I5).

## Architecture

```
agent action
  -> Gateway decide()         # PURE, never sees DNS (I4)
  -> allow
  -> Data Plane proxy: resolve(name)
       declared + allowed -> Endpoint -> HTTP mock -> ProxyTrace(target=name)   # A
       undeclared/blocked -> ResolutionDenied -> audit resolution_denied -> NO call   # C (fail-safe)
```

`resolve()` lives in the Data Plane (`recette/platform/netname/`), strictly
outside the decision path. `decide()` stays a pure function of (event, policy).

## Components

### 1. Config data (per server, in `config_store`)

- `fqdn: str | None` -- canonical internal name, e.g. `api.github.com` or
  `github.lab.internal`. Optional and back-compatible: a server without `fqdn`
  resolves by `id` as today.
- `aliases: list[str]` -- alternative names resolving to the same endpoint.
- `containment: bool` (global setting) -- enforce the allowlist (C). Off =
  realism only (A): unknown names fall back to the legacy id->endpoint behavior.

Validation in `recette/api/config_store.py`: `fqdn`/`aliases` are syntactic
hostnames; no two servers may declare the same `fqdn`/alias (collision = 422).

### 2. Resolver `recette/platform/netname/resolver.py`

- `resolve(name, table, *, containment) -> Endpoint | ResolutionDenied`.
- Pure: reads the server table only; no clock, no random, no socket. Stable
  iteration order. Deterministic (I4) and replay-stable.
- Resolution order: exact `fqdn` -> alias -> legacy `id` -> (containment on:
  `ResolutionDenied`; off: legacy fallback).
- `Endpoint` carries the existing mode-dependent address (`port` for
  `mock_local`/`honeypot`, `base_url` for `declared_url`/`real_saas`).

### 3. Proxy integration (`recette/platform/proxy/lab_proxy.py` + router)

- The proxy accepts a name, calls `resolve()`, and sets `base_url` from the
  returned `Endpoint`.
- `ProxyTrace.target` records the resolved name (the `fqdn`), not the IP:port.
- On `ResolutionDenied`: emit an audited `resolution_denied` platform event and
  return a fail-safe error WITHOUT making the HTTP call (deny-by-default).

### 4. Containment event (Audit Plane + red-team)

`resolution_denied` is a first-class audited event (event_id, agent_id, the
denied name, reason). It is the detectable exfil signal and maps to the
red-team standards (R23): OWASP ASI / MITRE ATLAS `AML.T0086` (exfiltration via
agent tool invocation). It does not enter the decision/replay path.

### 5. UX (everything operator-configurable)

- **Servers page** (`console/src/pages/servers/index.tsx`) -- `fqdn` + `aliases`
  inputs on the server CRUD form.
- **Containment toggle** -- a global switch "enforce private DNS allowlist"
  (Off = A only, On = A + C).
- **ServerTestPanel** -- a "resolve a name" probe: shows resolved endpoint or
  `denied`, before sending real traffic.
- **Proxy/trace view** -- shows the `fqdn` target and a `resolution_denied`
  badge when blocked.

### 6. API

- Existing server CRUD endpoints (`recette/api/routers/config.py`) accept
  `fqdn`/`aliases` in the body.
- New `POST /config/resolve` -- test a name (returns endpoint or denied).
- R16 contract gate: real fixtures + render-and-assert for the new server
  fields, the toggle, and the resolve panel.

## Data flow (failure modes)

- Unknown name + containment ON -> `ResolutionDenied` -> audited -> no call
  (fail-safe, never fail-open).
- Unknown name + containment OFF -> legacy id resolution (realism-only mode).
- Duplicate fqdn/alias at config write -> 422 (rejected before persistence).

## Determinism (I4)

`resolve()` is pure over the committed table; no DNS lookup mono-host. Same
(name, table) -> same Endpoint, this run and every replay. A replay test
asserts byte-stable resolution + a stable `resolution_denied` for a known
undeclared name. No `time`/`random`/socket in the path.

## Testing

- resolver: deterministic resolution; alias -> same endpoint; legacy id
  fallback when containment off; unknown -> `ResolutionDenied` (containment on).
- proxy: `ProxyTrace.target` carries the fqdn; denied path emits the audited
  event and makes NO call.
- config_store: fqdn/alias validation + collision 422.
- replay: byte-stable resolution + denial.
- coverage: every declared server resolves.
- console (R16): servers page new fields, containment toggle (both states),
  resolve panel, all against real fixtures.

## Phasing (B later, same source of truth)

The config server table is the single source of truth. When Control/Data/Audit
move to separate hosts (event-store Phase 2), the SAME table renders to a real
private resolver (CoreDNS zone / hosts file) managed by `recette.sh` (R19) --
no schema change, the resolver interface stays identical. Split-horizon
(`api.github.com` -> internal mock) is preserved.

## Constraints honoured

- I4: resolution pure + outside `decide()`; replay test.
- I2/I5: DNS is defense-in-depth; every action still traverses Gateway + proxy.
- Failure mode: deny-by-default on unknown name (fail-safe, never fail-open).
- R5: names live in the versioned config, not hardcoded.
- R19: no new hand-launched service mono-host; Phase 2 resolver owned by recette.sh.
- R16: console contract gate for the new UX.
- R23: `resolution_denied` mapped to OWASP ASI / ATLAS exfil.
