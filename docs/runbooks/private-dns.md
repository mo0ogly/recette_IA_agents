# Private DNS resolver -- runbook

> Lab servers carry stable internal names (`fqdn` + `aliases`) instead of raw
> `127.0.0.1:port`. The proxy resolves a name to a server entry deterministically
> (I4), records it as `ProxyTrace.target` (trace realism), and -- when global
> **containment** is on -- denies any undeclared name with an audited
> `resolution_denied` event and NO network call (fail-safe, an exfil signal).
>
> Design: `docs/plans/2026-06-15-private-dns-resolver-design.md`.
> Code: `recette/platform/netname/resolver.py` (pure), proxy gate in
> `recette/api/runners.py`, config in `recette/api/config_store.py`.

## The name model

Each server entry in `config/inspect_ia_agents.config.json` may declare:

- `fqdn` -- canonical internal name (e.g. `api.github.com`). Optional and
  back-compatible: a server without `fqdn` still resolves by its `id`.
- `aliases` -- alternative names that resolve to the same server.

A name resolves by `fqdn` -> `alias` -> `id`, in that order. Resolution is a
pure function of `(name, servers, containment)` -- no socket, no clock, no
random -- so it is replay-stable (I4) and never enters `decide()`.

## Containment (the allowlist gate)

A single global flag `containment` (top-level in the config) switches behavior:

- **off (default)** -- realism only: an unknown name falls back to the legacy
  `id` path. Nothing is denied.
- **on** -- the resolver is an allowlist: an undeclared name raises
  `ResolutionDenied`, the proxy emits an audited `resolution_denied` event, and
  makes NO call (fail-safe deny-by-default; defense-in-depth on top of proxy
  mediation, never a replacement for it).

## Operating from the console

Servers page (`/servers`):

- **Config tab** -- each server form has `FQDN (private DNS, optional)` and
  `Aliases (comma-separated)` fields, plus a global
  **Private-DNS containment** toggle (reads/writes `GET/PUT /config/containment`).
- **Test panel** (`ServerTestPanel`) -- a **Resolve name** probe hits
  `POST /config/resolve` and shows either the resolved endpoint
  (`name -> server_id (fqdn)`) or a `denied` badge with the reason. A denied
  probe is a successful diagnostic (HTTP 200, `resolved: false`), not an error,
  and appends no event.

## API

| Verb | Route | Body | Returns |
|------|-------|------|---------|
| GET  | `/config/containment` | -- | `{"containment": bool}` |
| PUT  | `/config/containment` | `{"enabled": bool}` | `{"containment": bool}` |
| POST | `/config/resolve` | `{"name": str, "containment"?: bool}` | resolved / denied dict |

`/config/resolve` outcomes (raw dict, no envelope):

```
resolved : {"name": "api.github.com", "resolved": true, "server_id": "gh-mock", "fqdn": "api.github.com"}
denied   : {"name": "evil.example.com", "resolved": false, "reason": "not_in_allowlist"}
legacy   : {"name": "<unknown>", "resolved": false, "reason": "unknown_legacy"}   # containment off
```

## Live proof (R14)

With the platform up (`./recette.sh platform up`, API on `:8090`):

```
curl -s -X POST http://localhost:8090/config/resolve -H 'content-type: application/json' -d '{"name":"api.github.com","containment":true}'
curl -s -X POST http://localhost:8090/config/resolve -H 'content-type: application/json' -d '{"name":"github.lab.internal","containment":true}'
curl -s -X POST http://localhost:8090/config/resolve -H 'content-type: application/json' -d '{"name":"evil.example.com","containment":true}'
```

Observed (2026-06-15): `api.github.com` and the alias `github.lab.internal` both
resolve to `gh-mock`; `evil.example.com` returns `resolved: false`,
`reason: not_in_allowlist` -- denied, no call.

## Gates

```
.venv/bin/python -m unittest discover -s tests
make recette
./recette.sh console-test
./recette.sh console-build
```

## Related

- `.claude/rules/determinism-replay.md` (I4) -- resolver is pure + replay-tested.
- `.claude/rules/frontend-contract-gate.md` (R16) -- console fixtures captured live.
- `docs/runbooks/lab-realistic-doubles.md` -- the lab doubles the names point at.
