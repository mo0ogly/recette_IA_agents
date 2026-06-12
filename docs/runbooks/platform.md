# Platform lab runbook -- governed execution (gateway + lab mock + e2e)

Operates the L1 docker lab: the AgentRail recette API (Gateway, Control/Audit
Plane) wired to the simulated external-systems lab, plus the end-to-end
governed-flow recette that proves the whole path.

## Architecture

Three planes, one governed path. No action reaches an external system without
a policy decision (I2), side effects only flow through the proxy (I5), every
step is an append-only audit event (I1).

```
        agent / console / curl
                 |
                 v
  +---------------------------------------------+
  | api (recette.api, :8090)        CONTROL     |
  |                                              |
  |  POST /actions/execute                       |
  |     |  capture timestamp (I4 input)          |
  |     v                                        |
  |  Gateway: resolve agent (config store, I3*)  |
  |     -> normalize to PlatformActionEvent      |
  |     -> policy decide (versioned, deny-by-    |
  |        default)                              |
  |          allow    -> execute via proxy       |
  |          deny     -> audit, never executed   |
  |          escalate -> pending, BLOCKED (I6)   |
  +-----------------+---------------------------+
                    | allow / approved only
                    v
  +---------------------------------------------+
  | LabHttpProxy (I5)               DATA         |
  |   POST http://lab-mock:8082/{target}/execute |
  |   -> side_effect_hash recorded               |
  +-----------------+---------------------------+
                    | every transition
                    v
  +---------------------------------------------+
  | SQLite event store (/data/events.db) AUDIT   |
  |   append-only, hash-chained (I1)             |
  |   GET /audit/events, GET /audit/verify       |
  +---------------------------------------------+
```

Docker services (docker-compose.yml):

| Service | Image target | Role |
|---------|--------------|------|
| `platform-init` | runtime (as root, one-shot) | chown the fresh `platform-data` volume to the non-root `recette` user |
| `lab-mock` | runtime | lab double of the 11 external systems, `:8082` |
| `api` | runtime | gateway + control/audit API, `:8090`, state on `platform-data` |
| `e2e` | audit | runs `tests/e2e/test_governed_flow.py` against `api` |

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | liveness |
| POST | `/actions/execute` | submit a governed action; `202` when escalated to pending |
| GET | `/actions/{event_id}` | stored event; `resolution` set once pending is resolved |
| GET | `/approvals?state=pending` | approval inbox (fold over the event log) |
| POST | `/approvals/{event_id}/approve` | resolve pending -> approved, executes via proxy |
| POST | `/approvals/{event_id}/deny` | resolve pending -> denied, never executed |
| POST | `/approvals/sweep-timeouts` | expire pendings; optional `{"now": ISO-8601}` (I4 input) |
| GET | `/audit/events` | event log query (`from_seq`, `agent_id`, `target_system`, `kind`, `limit`) |
| GET | `/audit/verify` | hash-chain verification report |
| GET | `/policies` | list policy versions |
| GET | `/policies/active` | active policy document |
| PUT | `/policies/active` | switch the active version (never mutates a document) |
| GET | `/policies/{version}` | one immutable version |
| POST | `/policies` | publish a new version |
| GET / POST | `/config/agents` | agent registry (identity source, see limitations) |
| PUT / DELETE | `/config/agents/{id}` | update / remove an agent |
| GET / POST / DELETE | `/config/ai-backends` | AI backend registry (no secrets stored, R8); 8 providers: anthropic, openai, gemini, groq, mistral, deepseek, xai, openai_compat (`base_url`) |
| POST | `/config/ai-backends/{id}/test` | connectivity probe (one minimal real call); always 200 with `{ok, latency_ms, error?}` -- fail-safe diagnostic, never a 500 |
| GET / POST | `/config/servers` | server registry: `mock_local` (port), `declared_url` (base_url, lab wire contract), `real_saas` (no proxy yet) |
| PUT / DELETE | `/config/servers/{id}` | update / remove a server entry |
| POST | `/config/servers/{id}/start`, `/stop` | lifecycle of a `mock_local` lab server (ServerManager); `{"status": "down", "error": ...}` is a domain result, not a transport error |
| GET | `/config/servers/{id}/status` | live status: process poll (`mock_local`), URL probe (`declared_url`), `n/a` (`real_saas`) |
| GET | `/config/servers/{id}/log?after=N` | incremental tail of the server's JSONL access log (cursor `next`) |
| GET | `/catalog/actions` | high-risk action catalog (verdicts + risk levels) |
| GET | `/agents`, POST `/agents/register` | Lane B agent catalog |
| POST | `/runs` | launch a run; `kind` = `lane_b` \| `discovery` \| `identification` \| `campaign` \| `replay` |
| GET | `/runs/{id}`, `/runs/{id}/events`, WS `/runs/{id}/ws` | run status, buffered frames, live frame stream |
| POST | `/runs/{id}/stop` | cooperative stop |
| GET / POST | `/campaigns` | list / create a persisted campaign (ordered agent launches) |
| GET / DELETE | `/campaigns/{id}` | one campaign / remove it |
| POST | `/campaigns/{id}/run` | run the campaign; streams via the run WebSocket, persists one recording per step |
| GET | `/recordings`, `/recordings/{id}` | list / fetch replayable recordings |
| POST | `/recordings/{id}/replay` | deterministically replay a recording (I4); the `replay_result` frame reports `matches_original` |

## Run kinds and frames

Every run is executed in a worker thread by the RunManager and emits frames
`{seq, type, data}` buffered on the run and pushed live to WebSocket
subscribers. First frame is always `start`, last is `end` with the final status.

| Kind | Body params | Domain frames |
|------|-------------|---------------|
| `lane_b` | `agent_id`, optional `stub_script` (mock; else the agent's `ai_backend` drives a live LLM, key from env, R8) | `step` (per agent action), `result` (recorded actions) |
| `discovery` | optional `surface` (default all) | `scorecard` per surface (total/passed/false_positives/false_negatives/all_passed) |
| `identification` | none | `agent_result` per agent (predicted vs expected verdict), final `scorecard` (+ detection_rate) |
| `campaign` | (via `/campaigns/{id}/run`) | `agent_start` / `step` / `agent_done` per step, final `campaign_done`; one recording persisted per step |
| `replay` | (via `/recordings/{id}/replay`) | `step` per replayed decision, `replay_result` with `matches_original` (I4) |

`capability_scope` is the set of catalog actions an agent may call (127
actions across 12 systems, `GET /agent-actions`), not a system name. The 11
canonical git actions (`read_repo` ... `trigger_ci`) are the github/gitlab
subset.

Per-agent target routing: an agent with a `server` binding executes through
a `ProxyForge` (real HTTP to the resolved server, I5); without one it keeps
the in-memory `LabForge`. A dangling or unsupported server reference fails
the run -- never a silent fallback.

## Environment variables (R5)

| Variable | Used by | Default | Docker lab value |
|----------|---------|---------|------------------|
| `AGENTRAIL_API_HOST` | api | `127.0.0.1` | `0.0.0.0` |
| `AGENTRAIL_API_PORT` | api | `8090` | `8090` |
| `AGENTRAIL_LAB_URL` | api (proxy) | `http://localhost:8082` | `http://lab-mock:8082` |
| `AGENTRAIL_EVENT_STORE_PATH` | api (audit) | `data/agentrail.events.db` | `/data/events.db` |
| `AGENTRAIL_POLICIES_DIR` | api (policy store) | `config/policies` | `/data/policies` |
| `AGENTRAIL_CONFIG_PATH` | api (agent/backend config) | `config/agentrail.config.json` | `/data/config.json` |
| `AGENTRAIL_CAMPAIGNS_PATH` | api (campaign catalogue) | `config/campaigns.json` | `/data/campaigns.json` |
| `AGENTRAIL_RECORDINGS_DIR` | api (replayable recordings) | `data/recordings` | `/data/recordings` |
| `AGENTRAIL_CORS_ORIGINS` | api (console cross-origin) | `http://localhost:5173,http://127.0.0.1:5173` | console origin(s) |
| `AGENTRAIL_LAB_PORT` | lab-mock | `8082` | `8082` |
| `AGENTRAIL_LAB_ACCESS_LOG` | lab-mock | unset (no log) | set by the ServerManager per managed server (`data/lab/{id}.access.jsonl`); one JSONL line `{event_id, target_system, action_type, resource, status}` per request -- the runtime capture surface for discovery |
| `AGENTRAIL_E2E_API_URL` | e2e tests | unset (suite skipped) | `http://api:8090` |
| `LAB_HOST_PORT` | compose port mapping | `8082` | host port for lab-mock |
| `API_HOST_PORT` | compose port mapping | `8090` | host port for api |
| `VITE_AGENTRAIL_API_URL` | console (Vite) | `http://localhost:8080` | set to the api URL |

## Failure modes (fail-safe, never fail-open)

| Failure | Behavior |
|---------|----------|
| Policy evaluation raises | default DENY + audited `platform_error` event; the action never executes |
| Unknown agent identity | DENY, audited (`deny_reason: unknown agent identity`) |
| Lab proxy down / non-2xx | audited `platform_error` event, `executed: false`, no bypass, no retry-around |
| Event store write fails on the deny/pending path | the action is not executed: an unaudited action must not run |
| Approval timeout | explicit `timeout` resolution via the sweep, never auto-approve (I6) |
| No active policy version | hard error -> DENY; the gateway never guesses a policy |

## Known limitations

- I3 is partial: agent identity is resolved from the config store by id. There
  is no cryptographic binding (no signed requests, no mTLS). Documented
  Phase-2 work.
- The approval service is a Temporal placeholder: pendings are a fold over the
  event log and timeouts are resolved by an explicit sweep endpoint, not by a
  durable workflow.
- `risk_score` is a static mapping from the catalog risk level
  (low/medium/high/critical), not a computed Risk Engine output.
- The lab mock is deterministic and stateless; it does not simulate external
  system failures (use the proxy failure mode tests for that).

## How to run

### Via `recette.sh` (recommended for local dev)

The simplest path -- starts the lab mock + API with the full platform wiring,
auto-picks a free port if 8090 is taken, and exposes the console and campaigns:

```
./recette.sh platform up
./recette.sh console start
./recette.sh campaign run identity-offboarding --json
./recette.sh platform status
./recette.sh platform down
./recette.sh platform purge
```

The resolved API port is persisted in `.run/api.port`; console and campaign
commands read it automatically. See
[recette-sh.md](recette-sh.md) for the full menu and command reference.

### Docker lab (build happens on first use)

```
make platform-lab
make platform-e2e
make platform-down
```

Manual smoke against the dockerized API (one command per line, R24):

```
curl -s http://localhost:8090/health
curl -s -X POST http://localhost:8090/config/agents -H "Content-Type: application/json" -d '{"id":"demo-admin","runtime":"lab","role":"identity_admin","capability_scope":["okta"]}'
curl -s -X POST http://localhost:8090/actions/execute -H "Content-Type: application/json" -d '{"agent_id":"demo-admin","action_type":"suspend_user","target_system":"okta","resource":"user:demo-1","payload":{}}'
curl -s "http://localhost:8090/approvals?state=pending"
curl -s -X POST http://localhost:8090/approvals/EV000000000000000001000001/approve -H "Content-Type: application/json" -d '{"approver":"ops","reason":"demo"}'
curl -s http://localhost:8090/audit/verify
```

Replace the `EV...` id with the `event_id` returned by the execute call.

Local run without docker (three terminals, or background the first two):

```
AGENTRAIL_LAB_PORT=8082 python3 -m recette.lab.mock_server
AGENTRAIL_LAB_URL=http://127.0.0.1:8082 AGENTRAIL_EVENT_STORE_PATH=/tmp/agentrail/events.db AGENTRAIL_POLICIES_DIR=/tmp/agentrail/policies AGENTRAIL_CONFIG_PATH=/tmp/agentrail/config.json python3 -m recette.api
AGENTRAIL_E2E_API_URL=http://127.0.0.1:8090 python3 -m unittest tests.e2e.test_governed_flow -v
```

The e2e suite is opt-in: without `AGENTRAIL_E2E_API_URL` all of its tests are
skipped, so the normal `make test` suite stays offline-green.

State persistence: the docker lab keeps the event store, policies and agent
config on the `platform-data` named volume. `make platform-down` keeps it;
`docker compose down -v` wipes it (fresh hash chain, empty inbox).

## Console

The approval console (React/Vite) talks to the API directly:

```
cd console
VITE_AGENTRAIL_API_URL=http://localhost:8090 npm run dev
```

Or `make console` from the repo root (uses the console's own env defaults;
set `VITE_AGENTRAIL_API_URL` in `console/.env.local` to point at the lab API).
