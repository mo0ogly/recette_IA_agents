# Platform lab runbook -- governed execution (gateway + lab mock + e2e)

Operates the L1 docker lab: the inspect_ia_agents API (Gateway, Control/Audit
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
| POST | `/config/servers/{id}/test` | fire one action (`{action_type, resource?, payload?}`) at the server through the run proxy (I5); returns `{ok, latency_ms, status_code, response, side_effect_hash, error?}` -- fail-safe (server down / bad action -> `ok:false`, never a 500); unknown id 404, `real_saas` 400 |
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
| `INSPECT_IA_AGENTS_API_HOST` | api | `127.0.0.1` | `0.0.0.0` |
| `INSPECT_IA_AGENTS_API_PORT` | api | `8090` | `8090` |
| `INSPECT_IA_AGENTS_LAB_URL` | api (proxy) | `http://localhost:8082` | `http://lab-mock:8082` |
| `INSPECT_IA_AGENTS_EVENT_STORE_PATH` | api (audit) | `data/inspect_ia_agents.events.db` | `/data/events.db` |
| `INSPECT_IA_AGENTS_POLICIES_DIR` | api (policy store) | `config/policies` | `/data/policies` |
| `INSPECT_IA_AGENTS_CONFIG_PATH` | api (agent/backend config) | `config/inspect_ia_agents.config.json` | `/data/config.json` |
| `INSPECT_IA_AGENTS_CAMPAIGNS_PATH` | api (campaign catalogue) | `config/campaigns.json` | `/data/campaigns.json` |
| `INSPECT_IA_AGENTS_RECORDINGS_DIR` | api (replayable recordings) | `data/recordings` | `/data/recordings` |
| `INSPECT_IA_AGENTS_CORS_ORIGINS` | api (console cross-origin) | `http://localhost:5173,http://127.0.0.1:5173` | console origin(s) |
| `INSPECT_IA_AGENTS_LAB_PORT` | lab-mock | `8082` | `8082` |
| `INSPECT_IA_AGENTS_LAB_ACCESS_LOG` | lab-mock | unset (no log) | set by the ServerManager per managed server (`data/lab/{id}.access.jsonl`); one JSONL line `{event_id, target_system, action_type, resource, status}` per request -- the runtime capture surface for discovery |
| `INSPECT_IA_AGENTS_E2E_API_URL` | e2e tests | unset (suite skipped) | `http://api:8090` |
| `LAB_HOST_PORT` | compose port mapping | `8082` | host port for lab-mock |
| `API_HOST_PORT` | compose port mapping | `8090` | host port for api |
| `VITE_INSPECT_IA_AGENTS_API_URL` | console (Vite) | `http://localhost:8080` | set to the api URL |

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
INSPECT_IA_AGENTS_LAB_PORT=8082 python3 -m recette.lab.mock_server
INSPECT_IA_AGENTS_LAB_URL=http://127.0.0.1:8082 INSPECT_IA_AGENTS_EVENT_STORE_PATH=/tmp/inspect_ia_agents/events.db INSPECT_IA_AGENTS_POLICIES_DIR=/tmp/inspect_ia_agents/policies INSPECT_IA_AGENTS_CONFIG_PATH=/tmp/inspect_ia_agents/config.json python3 -m recette.api
INSPECT_IA_AGENTS_E2E_API_URL=http://127.0.0.1:8090 python3 -m unittest tests.e2e.test_governed_flow -v
```

The e2e suite is opt-in: without `INSPECT_IA_AGENTS_E2E_API_URL` all of its tests are
skipped, so the normal `make test` suite stays offline-green.

Agent+server e2e smoke (managed mock server, bound agent, campaign, access-log
capture, deterministic replay) against any running API:

```
python3 scripts/smoke_lab.py --api http://127.0.0.1:8090 --server-port 9111
```

Exit 0 = `SMOKE PASS` (all six steps asserted). Re-runnable back to back: the
script deletes its own fixture entities (`smoke-*`) up front and reads the
access log from a cursor, so prior runs never pollute the assertions.

Shorthand (starts the API if needed, then runs the lab smoke):

```
./recette.sh smoke
make smoke
```

Browser smoke (closes the chain console -> API -> mock server -> replay in a
real Chromium): drives the actual UI -- /servers Start->up, /campaigns
Lancer->completed, /servers Stop->down, recording visible, Replay->completed
(I4). Needs a running console pointed at the API and the chromium browser
(`python3.11 -m playwright install chromium`):

```
VITE_INSPECT_IA_AGENTS_API_URL=http://127.0.0.1:8090 npm --prefix console run dev -- --port 5173 --strictPort
python3.11 scripts/smoke_console.py --console http://localhost:5173 --api http://127.0.0.1:8090 --server-port 9131
```

The console origin must be in the API CORS allow-list (`INSPECT_IA_AGENTS_CORS_ORIGINS`,
default `localhost:5173` + `127.0.0.1:5173`); a non-default console port needs
that port added or the browser fetch is blocked. Uses the Python Playwright
bindings (system python3.11 here; the [api] venv has fastapi but not
playwright).

State persistence: the docker lab keeps the event store, policies and agent
config on the `platform-data` named volume. `make platform-down` keeps it;
`docker compose down -v` wipes it (fresh hash chain, empty inbox).

## Console

The approval console (React/Vite) talks to the API directly:

```
cd console
VITE_INSPECT_IA_AGENTS_API_URL=http://localhost:8090 npm run dev
```

Or `make console` from the repo root (uses the console's own env defaults;
set `VITE_INSPECT_IA_AGENTS_API_URL` in `console/.env.local` to point at the lab API).

## Server registry (mock_local / declared_url / real_saas)

Servers are CRUD entities in `config/inspect_ia_agents.config.json` (`servers` section)
and in the console Servers tab. Three modes:

- `mock_local`: the platform launches a real local HTTP process
  (`python -m recette.lab.mock_server`) on the configured port. Start/stop from
  the console or `POST /config/servers/{id}/start|stop`. `GET /health` probes it.
  Every request received is appended to `data/lab/{id}.access.jsonl` and served
  back by `GET /config/servers/{id}/log?after=N` (the console log panel tails it).
- `declared_url`: any external server speaking the lab wire format
  (`POST /{target_system}/execute`, `{"success","data"}` envelope).
- `real_saas`: reserved; execution fails explicitly until realmode proxy wiring lands.

An agent carrying `"server": "<id>"` executes through the proxy resolved from the
registry (I5). A dangling reference fails the run explicitly -- never a silent
fallback. Demo flow verified live:

```bash
curl -X POST localhost:8090/config/servers -d '{"id":"okta-mock","system":"okta","mode":"mock_local","port":9122}' -H 'Content-Type: application/json'
curl -X POST localhost:8090/config/servers/okta-mock/start
curl -X POST localhost:8090/config/servers/okta-mock/test -H 'Content-Type: application/json' -d '{"action_type":"suspend_user","resource":"user:jdoe"}'
curl -X POST localhost:8090/runs -H 'Content-Type: application/json' -d '{"kind":"lane_b","params":{"agent_id":"okta-rogue","stub_script":[{"kind":"tool_call","tool_name":"suspend_user","tool_args":{"resource":"user:jdoe"}},{"kind":"final","text":"done"}]}}'
curl "localhost:8090/config/servers/okta-mock/log?after=0"
```

Note: lab domain handlers simulate the catalog risk-action set; canonical
read-style actions (`read_repo`, `open_pr`) are not simulated by the github
domain and return 404 (the run then fails explicitly, by design).

### The lab servers (config-driven, one per target system)

The `servers` section of the config ships one `mock_local` server per
`target_system` an agent can face. The set is CONFIG-DRIVEN and grows with the
corpus (do not hardcode a count); ports run 9101+. As of 2026-06-14 there are 8:

| Server id | `system` | port |
|-----------|----------|------|
| `gh-mock` | github | 9101 |
| `okta-mock` | okta | 9102 |
| `finance-mock` | finance | 9103 |
| `support-desk-mock` | support_desk | 9104 |
| `slack-mock` | slack | 9105 |
| `cloud-mock` | cloud | 9106 |
| `hris-mock` | hris | 9107 |
| `legal-dms-mock` | legal_dms | 9108 |

An agent that hits a real HTTP target binds it through its `server` field (an
agent with no `server` falls back to the in-process LabForge). All servers run
the SAME `recette.lab.mock_server` (it serves every domain); the `system`/port
pair just gives each agent family its own endpoint. An unstarted server makes a
bound run fail with `target server ... unreachable` (fail-safe, no fallback, I5).

`./recette.sh platform up` starts every `mock_local` server automatically (once
the API is healthy, `cicd/platform.sh::_lab_servers_start` reads the `servers`
list and POSTs `/config/servers/{id}/start` for each -- so a new server needs no
script change). They are owned by the API's ServerManager, so `platform down`
(API shutdown) tears them down; `platform status` lists each with its live
up/down. To (re)start one by hand:

```bash
curl -X POST localhost:8090/config/servers/support-desk-mock/start
```

### Editing a lab domain: hot-reload (no restart)

The mock_local servers are long-lived and load each domain once. With
`INSPECT_IA_AGENTS_LAB_RELOAD` on (R5; `platform up` sets it, OFF by default for
test/replay determinism, I4), `mock_server` reloads a `recette/lab/domains/*.py`
module whose source changed, so an edited handler is served WITHOUT a restart.
Only servers STARTED with the flag self-reload; one started before it keeps
serving stale code (symptom: a thin `status: simulated` body in the cockpit
exchange) until it is restarted.

### Agents page: four tabs

The Agents page has four tabs:

- **Configuration** -- the agent CRUD table + form; the per-row *Run* button
  fires a quick run of the stored scenario.
- **Corpus** -- read-only browser of the ground-truth subjects (`GET /subjects`,
  the `CorpusPage` component reused here; the standalone `/corpus` route still
  deep-links). Every test subject across families (git_agent, maf_agent,
  maf_orchestration) with its category, broken axis (violation_type) and
  expected verdict.
- **Cockpit -- lancer & debug** -- the detailed launcher + live flux + network
  log.
- **Run log** -- the live frame journal (start/step/result/end) of the last run
  started from the Configuration table's *Run* button.

#### Corpus vs Cockpit -- the answer key vs the exam

The single most-confused distinction, stated as a school exam so the recette
team never mixes them up:

- **Corpus = the marked answer key.** For each agent, the expected verdict
  (correct or not, and why). Frozen, read-only -- you launch nothing here. It is
  the ground truth an external tool is judged against.
- **Cockpit = sitting the exam.** You launch an agent; it acts for real against
  the lab and produces its paper (the action-log: what it *did*).
- **The recette = marking the paper against the key.** Compare what the agent
  did (Cockpit) to the expected answer (Corpus). Match = pass.

Key point: an agent is never judged on what it *declares* (its manifest/code)
but on what it *does* -- the network exchange in the log. The declaration can
lie; the act cannot. Each tab carries a one-line plain-language reminder of its
role (`TAB_NOTES` in `console/src/pages/agents/index.tsx`).

### Cockpit network log (proxy traces)

The Cockpit (a tab of the Agents page) shows, under the launch panel, the
side-effect PROXY traces (I5) for the active run -- the real network calls the
agent made to its bound server (`action target/resource -> status`), failures
included. This is the debug view; the governed audit log never sees lane_b runs.
It is gated by `INSPECT_IA_AGENTS_PROXY_DEBUG` (R5, off by default; `platform up`
sets it on): otherwise `/proxy` and this panel record nothing (the panel says so
instead of showing a silent empty box).

Clicking a trace line (or the auto-selected latest) opens the **agent <-> server
exchange** in the Monaco viewer: the `request_payload` the agent sent and the
server `response` it got back. An **Afficher** select narrows it to the agent
request only, the server response only, or both. Two more selects (**Agent** /
**Serveur**, default **Tous**) filter the displayed lines to the values present
in the run. Only agents bound to a `server` (HTTP proxy) trace; a `server`-less
agent runs in in-process LabForge and produces no network call.

The trace carries the server `response` body (`ProxyTrace.response`, from
`ExecutionResult.response`); a thin `status: simulated` body usually means the
mock_local server is serving stale domain code -- see the hot-reload note above.

## AI providers

`recette/llm.py` backends: anthropic, openai, gemini, groq, mistral, deepseek,
xai, plus `openai_compat` (any OpenAI-wire vendor via `base_url` -- Ollama,
OpenRouter, vLLM...). Keys via env only: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
`GEMINI_API_KEY`, `GROQ_API_KEY`, `MISTRAL_API_KEY`, `DEEPSEEK_API_KEY`,
`XAI_API_KEY`. `POST /config/ai-backends/{id}/test` makes one minimal live call
and returns `{ok, latency_ms, kind|error}` -- wired to the Test button in the
console AI Backends panel.

## Verdict scoring (recette of the external tool)

Agents may carry a `ground_truth` block (`detectable`, `expected_identity`,
4 `dimensions`, `expected_verdict`). The external discovery/identification tool
pushes its results:

```bash
curl -X POST localhost:8090/verdicts -H 'Content-Type: application/json' -d '{"tool":"discovery-v1","results":[{"agent_id":"demo-gh-bot","detected":true,"verdict":"correct","identity":"bot@acme","dimensions":{"identity":true,"capabilities":true,"policy":true,"behavior":true}}]}'
curl localhost:8090/verdicts/scorecard
```

Each result is judged against the agent ground truth (PASS/FAIL/SKIP + per-check
detail + evidence event ids from the audit log). `GET /verdicts/scorecard`
aggregates detection rate, per-dimension accuracy, false positives/negatives.
The console Verdicts tab renders the banner, the per-agent table (expandable
evidence) and accepts a JSON upload as an alternative to the HTTP push.

### Submit a finished run as a verdict (internal loop)

Beyond the external tool, a run launched in the console can be pushed onto the
same board without any external tool. `POST /runs/{id}/submit-verdict` judges
the run's real action log (`judge_run`, pure/deterministic I4), shapes it as a
`/verdicts` result entry (`detected:true`, `identity=principal`, the run verdict
+ 4 dimensions) and stores it through the shared judge path under the tool name
`run:<id>`:

```bash
RUN=$(curl -sX POST localhost:8090/runs -H 'Content-Type: application/json' -d '{"kind":"lane_b","params":{"agent_id":"demo-gh-bot","stub_script":[{"kind":"tool_call","tool_name":"read_repo","tool_args":{"resource":"acme/x"}},{"kind":"final","text":"done"}]}}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["run_id"])')
curl -sX POST localhost:8090/runs/$RUN/submit-verdict
curl -s localhost:8090/verdicts
```

It is judged against the same `ground_truth`, so an agent without ground truth
yields SKIP (never a vacuous PASS). In the console this is the "Soumettre aux
Verdicts" button (agent eye -> Verdict tab) and the dashboard's auto-submit at
run end -- closing the launch -> act -> judge -> Verdicts loop. `GET
/verdicts/history` lists every submission (tool/run, seq, PASS/FAIL/SKIP), shown
in the console "Historique des soumissions" panel.

## Observability surfaces for the external tool

1. Real HTTP traffic against mock_local servers (sniff/scan the ports).
2. `GET /audit/events` (filterable) and `GET /audit/export.jsonl` (full NDJSON
   stream of the append-only event log, hash-chained).
3. The REST API itself (agents, servers, runs, campaigns, verdicts).
