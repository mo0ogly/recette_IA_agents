# Runbook -- Track U Recette API (U1)

The U1 API (`recette/api/`) exposes every CLI capability -- identification /
discovery / Lane B runs, config, catalog -- over HTTP plus a WebSocket live event
stream. It reuses the `recette` package directly (no business logic duplicated) and
the core `recette` package never imports `recette.api` -- FastAPI is an optional extra.

## Install

```bash
pip install -e '.[api]'
```

(or use the project `.venv`, which already has the `[api]` extra installed).

## Run

```bash
make api
# or
python -m recette.api
```

Host/port via env (defaults `127.0.0.1:8090`):

| Env var | Default |
|---------|---------|
| `AGENTRAIL_API_HOST` | `127.0.0.1` |
| `AGENTRAIL_API_PORT` | `8090` |

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | liveness |
| GET | `/agents` | catalog (identification corpus, discovery surfaces, registered lane_b agents) |
| POST | `/agents/register` | register a Lane B agent into config |
| GET/POST/PUT/DELETE | `/config/agents[/{id}]` | Lane B agent config CRUD |
| GET/POST/DELETE | `/config/ai-backends[/{id}]` | AI backend config CRUD (no secrets stored) |
| POST | `/runs` | launch a run `{kind: identification\|discovery\|lane_b, params}` |
| GET | `/runs/{id}` | run status |
| GET | `/runs/{id}/events` | buffered event frames (polling fallback) |
| POST | `/runs/{id}/stop` | request cooperative stop |
| WS | `/runs/{id}/ws` | live event-frame stream (WebSocket transport) |

## WebSocket usage

Connect to `ws://host:port/runs/{id}/ws`. The server pushes JSON frames of the form
`{seq, type, data}`. The stream ends with a terminal frame:

```json
{"type": "end", "data": {"status": "..."}}
```

## Lane B run example

Deterministic / offline (provide a `stub_script`):

```json
POST /runs
{"kind": "lane_b", "params": {"agent_id": "a1", "stub_script": [...]}}
```

Without `stub_script`, the agent's `ai_backend_id` resolves to a live provider
(provider key supplied via env -- R8).

## Real-mode guard

Lab is the default forge (no side effects). Real-mode forge is **not** enabled in U1
unless a future task wires `params.real` plus `AGENTRAIL_REAL_ALLOWLIST` (env).

Secrets (provider keys, tokens) are never stored in config -- always via env (R8).

## Follow-up note

The API assumes a single-user lab; authentication is a later Track U follow-up.
