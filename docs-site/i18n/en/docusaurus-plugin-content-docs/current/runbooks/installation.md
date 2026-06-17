# Installation and startup -- inspect_ia_agents

This doc installs the project and launches, **exclusively via `./recette.sh`**
(R19 -- single entry point), the two families of servers:

- the **application server**: the governed API (`:8090`) + the console UX (`:5173`);
- the **servers called by the agents**: the mock lab (`:8082`) plus the 12
  per-domain servers (`:9101`-`:9112`) that simulate the 16 governed systems
  (okta, github, gitlab, finance, slack, comms, compliance, ...). This is what an
  agent touches when it executes an action -- never a real SaaS by default (lab
  forge, zero side effects, I5).

> `./recette.sh platform up` starts the mock lab THEN the API **in order**: a
> single command covers both the application server and the servers called by the
> agents.

---

## 1. Prerequisites

| Tool | Version | Role |
|-------|---------|------|
| Python | >= 3.11 | recette, mock lab, API |
| Node.js + npm | >= 20 | console UX (vite) |
| bash, curl, ss | -- | `recette.sh` and its health probes |

The mock lab (the servers called by the agents) is **pure stdlib**: no
dependency to install for it. Only the API needs the `[api]` extra
(FastAPI + uvicorn).

---

## 2. Get the code

```
git clone <url-du-repo> recette_agentrail
cd recette_agentrail
```

---

## 3. Install the dependencies

### 3a. Python (project venv)

`recette.sh` automatically uses `.venv/bin/python` if it exists, otherwise the
system `python3`. Create the venv and install the API extra:

```
python3 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -e '.[api]'
```

`-e '.[api]'` pulls in `jsonschema` (recette core) + `fastapi` + `uvicorn`
(application server). Optional extras depending on your needs: `.[real]` (real
GitHub/GitLab), `.[dev]` (ruff/mypy/pytest), `.[bundle]`, `.[postgres]`, `.[nats]`.

### 3b. Console UX (Node)

Nothing to do by hand: `./recette.sh console start` runs `npm install` on the
first startup.

---

## 4. Launch the servers via `recette.sh`

```
./recette.sh platform up
./recette.sh console start
```

- `platform up` starts the **mock lab `:8082`** + the 12 per-domain servers
  (`:9101`-`:9112`, the 16 systems called by the agents) then the **governed API
  `:8090`** (or the first free port in 8090-8099, persisted in `.run/api.port`).
- `console start` launches the **console `:5173`**, automatically wired to the
  resolved API port (`VITE_INSPECT_IA_AGENTS_API_URL`).

Then open **http://localhost:5173** (the graphical UX; the API `:8090` is JSON,
`GET /` there returns `404` -- this is normal).

### Additional target servers

The mock lab `:8082` is the server called by default. To wire in other targets
(a dedicated local mock, a declared URL, a real SaaS), declare them in the
**Servers** tab of the console -- they are started/stopped on demand by the API
(`mock_local` launches its own process; `declared_url` points to an existing URL;
`real_saas` hits a real system). Those servers do not go through `recette.sh` but
through the console / the API.

---

## 5. Verify

```
./recette.sh platform status
curl -s http://127.0.0.1:8082/healthz        # mock lab (agent servers)
curl -s http://127.0.0.1:8090/health         # application API (adjust the port via .run/api.port)
```

`platform status` shows the pid/port of each service and the state of the audit
chain (`GET /audit/verify`).

---

## 6. Stop

```
./recette.sh platform down       # clean shutdown of lab + API (+ console)
./recette.sh console stop        # console only
./recette.sh platform purge      # if a local server of the repo got stuck
```

`purge` only sweeps processes anchored in THIS repo (API, lab, vite); never a
Docker container nor an external process.

---

## 7. Ports and configuration

| Service | Default port | Override (env, R5) |
|---------|-------------|--------------------|
| application API | 8090 (auto 8090-8099) | `INSPECT_IA_AGENTS_API_PORT` |
| mock lab (agent servers) | 8082 | `INSPECT_IA_AGENTS_LAB_PORT` |
| console UX | 5173 | `INSPECT_IA_AGENTS_CONSOLE_PORT` |

Defaults in `cicd/lib/common.sh`. Runtime state under `.run/` (`api.pid`,
`api.port`, `lab.pid`, `console.pid`, `*.log`). No secret stored (R8) -- the
credentials of real systems come from the environment.

---

## 8. See also

- Complete operator guide (interactive menu + all commands):
  [recette-sh.md](recette-sh.md).
- Architecture, Control/Data/Audit planes, agent types: [../ARCHITECTURE.md](../ARCHITECTURE.md).
- Track U API: [api.md](api.md). Platform + e2e: [platform.md](platform.md).
