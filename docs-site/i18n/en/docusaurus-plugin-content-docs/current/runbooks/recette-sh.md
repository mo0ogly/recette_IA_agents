# Operator guide -- `recette.sh` and the inspect_ia_agents application

`recette.sh` is the single entry point for driving the entire inspect_ia_agents
recette (acceptance testing): the legacy Docker lab (discovery/identification),
the Track U API, and the **governed execution platform** (gateway + console UX +
campaigns) added in wave 1.

Two usage modes:

```
./recette.sh            # menu interactif
./recette.sh <cmd> ...  # CLI non interactif (delegue aux sous-programmes cicd/)
```

The script only orchestrates; each domain lives in `cicd/<domaine>.sh`
(`docker.sh`, `api.sh`, `platform.sh`, `checks.sh`, `git.sh`, `status.sh`),
with shared helpers in `cicd/lib/common.sh`.

---

## 1. What is the application?

It is a **recette platform for the discovery and identification tools** of
inspect_ia_agents -- NOT those tools themselves. It produces the test subjects
(agents that you configure, launch, stop) and measures whether the discovery
tool spots them and whether identification returns the right verdict, by
comparison against the ground-truth. The cockpit (`http://localhost:5173`)
drives everything: configure agents (mock or real AI), launch / stop them, run
persisted campaigns with deterministic replay (I4), score discovery +
identification.

The **governance** building blocks below (gateway, policy, approvals, audit) are
the target platform, present here as a **mock** (secondary tabs); they serve as
a reference context, not as the current recette path.

### Runtime governance (mock, reference)

An agent never touches an external system without:

1. a resolved **identity** (I3),
2. a **policy decision** `allow | deny | escalate` (I2, deny-by-default),
3. in the case of `escalate`, a **blocking human approval** -- nothing executes
   until it is approved (I6),
4. a **side effect mediated** by a proxy that produces a `side_effect_hash`
   (I5),
5. an **immutable audit event** chained by hash (I1).

### The three planes

```
        agent / console / campagne / curl
                       |
                       v
   CONTROL  Gateway (recette/platform/gateway.py)
            resolve identite -> normalise en PlatformActionEvent
            -> policy decide (versionnee, deny-by-default)
                 allow    -> execute via proxy
                 deny     -> audite, jamais execute
                 escalate -> pending, BLOQUE (I6)
                       |
                       v
   DATA     LabHttpProxy (I5) -> lab mock :8082 /{systeme}/execute
            -> side_effect_hash enregistre
                       |
                       v
   AUDIT    Event store SQLite append-only, hash-chaine (I1)
            GET /audit/events, GET /audit/verify
```

### The catalog: 146 sensitive actions / 16 systems (Annex C criticality C1-C4)

Source of truth: `docs/tracking/PLAN_high-risk-action-catalog_2026-06-12.md`.
Code: `recette/platform/catalog/domains/<systeme>.py` (1 module per system).

| System | `target_system` | Action examples |
|---------|-----------------|--------------------|
| Identity / Access | `okta` | suspend_user, delete_user, disable_sso |
| GitHub / DevOps | `github` | delete_repository, disable_branch_protection |
| CRM / Sales | `crm` | export_customer_base, bulk_modify_deals |
| Finance | `finance` | launch_wire_transfer, trigger_refund |
| Data | `data_platform` | delete_logs, extract_data_to_external_llm |
| Slack | `slack` | send_message_as_executive, export_slack_history |
| Support | `support_desk` | export_customer_conversations, delete_ticket |
| Cloud | `cloud` | delete_database, delete_kms_key |
| HR | `hris` | modify_salary, export_employee_data |
| Legal | `legal_dms` | delete_evidence_item, accept_contract_terms |
| Product | `product_cms` | publish_production, modify_pricing |

Each action carries the expected verdict (most are `escalate` for an authorized
role, `deny` otherwise; a few actions are an absolute `deny` for everyone, e.g.
`delete_logs`, `delete_audit_evidence`, `disable_sso`, `delete_backups`,
`delete_kms_key`, `send_message_as_executive`, `delete_evidence_item`) and a
risk level (low/medium/high/critical).

### The UX cockpit (React/Vite, `console/` directory)

The cockpit produces the **test subjects** that the discovery / identification
tools must spot and judge. It is NOT the discovery tool. Six tabs, wired
directly to the API. Detail: [console/README.md](../../console/README.md).

| Tab | Role |
|--------|------|
| **Cockpit** | choose an agent, mock mode (deterministic script) or real AI (ai_backend, env key), launch it, follow the live flow, stop it |
| **Recette** | run discovery + identification on the corpus -> scorecard detected/distinguished vs ground-truth (per surface / per agent) |
| **Campagnes** | persisted agent sets launched on demand; live flow; replayable recordings with an IDENTICAL/DIVERGENT verdict (deterministic replay, I4) |
| **Agents** | define each agent (principal, target_system, goal, capability_scope = canonical actions, ai_backend) + CRUD of the ai-backends (provider+model, zero secret R8) |
| **Catalog** (mock governance) | the 146 actions (criticality C1-C4) + policy editor |
| **Approvals** (mock governance) | approvals inbox (I6) |
| **Audit** (mock governance) | immutable journal + hash chain |

Each tab carries a detailed `? Aide` modal. The Catalog / Approvals / Audit tabs
are the governance platform (mock), kept secondary, not the discovery recette
path.

`capability_scope` = the list of **canonical actions** that the agent can call
(`read_repo, list_repos, read_ci, open_issue, comment_issue, open_pr, merge_pr,
push, manage_webhook, manage_release, trigger_ci`), not a system name.

### The campaigns (`recette/campaign.py`, `campaigns/` directory)

A **campaign** is a declarative JSON file: the agents to create + an ordered list
of actions to submit, with an optional expected verdict per action. The runner
goes through the **real governed path** (nothing is bypassed), verifies the audit
chain, writes a JSON report, and exits with a non-zero code if a verdict does not
match -- so it is usable as a black-box recette.

Shipped campaigns:

| Campaign | Content | Expected result |
|----------|---------|------------------|
| `identity-offboarding` | offboarding by an identity admin | 3 escalate (pending) + 1 deny (`disable_sso`) |
| `finance-payment-run` | batch of payments by admin + unauthorized bot | 3 escalate + 2 deny |
| `redteam-probe` | 9 forbidden actions across 7 systems by an unauthorized bot | 9 deny, chain intact |

---

## 2. The interactive menu

`./recette.sh` (with no argument) displays:

```
  Docker lab
   1) Statut global              5) Rebuild image
   2) Demarrer le lab (up)       6) Logs lab
   3) Arreter le lab (down)
   4) Redemarrer le lab
  API Track U
   7) API start    8) API stop    9) API statut
  Checks
  10) Tests (local)   11) Gates (local)   12) Report (local)   13) Tests (docker)
  Git
  14) Git statut   15) Git pull   16) Git push   17) Git sync
  Plateforme gouvernee
  18) Plateforme up (lab mock + API)
  19) Plateforme down
  20) Plateforme statut
  21) Console UX start (http://localhost:5173)
  22) Console UX stop
  Campagnes
  23) Lister les campagnes
  24) Lancer une campagne
  Nettoyage
  25) Purger les serveurs web locaux (API, lab, console)
   0) Quitter
```

### Section details

**Docker lab (1-6)** -- legacy discovery/identification lab (`cicd/docker.sh`).
Builds the image, starts `discovery-mock`, runs the discovery recette over HTTP.
Unrelated to the governed platform.

**API Track U (7-9)** -- starts/stops the *bare* API (`cicd/api.sh`,
`python -m recette.api`) without the platform wiring. For the full platform,
prefer entry 18.

**Checks (10-13)** -- unittest tests, gates (ruff/mypy/bandit), report, docker
variant (`cicd/checks.sh`).

**Git (14-17)** -- status, pull, push, sync (`cicd/git.sh`).

**Governed platform (18-22)** -- the wave 1 core (`cicd/platform.sh`):

- **18 Platform up**: starts the mock lab (:8082 + 12 servers :9101-:9112, 16
  simulated systems) THEN the API with all the wiring (lab URL, SQLite event
  store, policies directory). Automatically picks a free port (8090-8099) if 8090
  is occupied by another local service, and persists it in `.run/api.port`.
- **19 Platform down**: stops API + lab (+ console if started).
- **20 Platform status**: pid/port of each service + `GET /audit/verify`
  (state of the hash chain).
- **21 Console UX start**: `npm install` on first launch, then vite dev on :5173,
  with `VITE_INSPECT_IA_AGENTS_API_URL` wired to the resolved API port.
- **22 Console UX stop**.

**Campaigns (23-24)**:

- **23 List**: enumerates `campaigns/*.campaign.json` (name + number of actions).
- **24 Run**: interactive selector, runs the campaign against the running API,
  writes a timestamped report under `.run/campaigns/`.

**Cleanup (25)**:

- **25 Purge**: cleanly stops lab/API/console, then sweeps the leftover
  `recette.api`, `recette.lab.mock_server` and vite processes **anchored in this
  repo only** (path verification in the process arguments). It **never** touches
  a Docker container nor a process outside the repo. Cleans up the pid/port files
  and shows the ports still being listened on for control. Use it when a local
  project server has stayed stuck or when the pid files have been lost.

---

## 3. Non-interactive CLI

Command-line equivalents (same sub-programs):

```
./recette.sh up|down|restart|rebuild|ps        # docker lab
./recette.sh logs [svc]|shell [svc]            # docker lab
./recette.sh status                            # snapshot global
./recette.sh api start|stop|restart|status|logs
./recette.sh platform up|down|restart|status|purge
./recette.sh console start|stop|status|logs
./recette.sh campaign list|run <nom> [--json]
./recette.sh test|gates|report|validate|run|discovery [--docker]
./recette.sh wire up|down|status|logs|ca       # overlay mitmproxy (interception wire, optionnel)
./recette.sh llm-proxy up|down|status|logs     # overlay LiteLLM (gateway LLM, optionnel)
./recette.sh git status|pull|push|sync|branches|clean-merged
./recette.sh --help
```

Both overlays are optional, OFF by default, and never enter the deterministic
path (I4). `wire` = network view of the agent -> target system calls (see
[proxy-debug-console.md](proxy-debug-console.md)); `llm-proxy` = an
OpenAI-compatible gateway centralizing the LLM calls (see
[llm-gateway-litellm.md](llm-gateway-litellm.md)).

`campaign run` accepts a short name (`identity-offboarding`), a file name or a
path; `--json` writes the report under `.run/campaigns/`.

---

## 4. Typical walkthrough (from zero to an approval)

```
./recette.sh platform up
./recette.sh console start
```

Then open `http://localhost:5173` (the **Cockpit** tab):
1. **Agents** tab: create an agent (id, principal, target_system, goal,
   capability_scope = canonical actions); optionally an ai-backend.
2. **Cockpit** tab: choose the agent, **mock** mode, **Launch** -> the live flow
   shows each step (`step read_repo -> github`), then `end completed`.
3. **Recette** tab: **Launch discovery** and **Launch identification** ->
   scorecards detected/distinguished vs ground-truth.
4. **Campagnes** tab: create a campaign (check some agents), **Launch**, then
   **Replay** on a recording -> IDENTICAL verdict (determinism I4).

> Two notions of "campaign" coexist: the cockpit **Campagnes** tab (discovery
> recette campaigns, persisted Lane B agents + replay, via the API `/campaigns`)
> and the `./recette.sh campaign` CLI (legacy governance campaigns =
> allow/deny/escalate actions, `campaigns/*.campaign.json`). The former is the
> current path; the latter is kept for the governance platform (mock).

At the end:

```
./recette.sh platform down      # arret propre
./recette.sh platform purge     # si un serveur est reste bloque
```

---

## 5. Ports and why `:8094/` returns `{"detail":"Not Found"}`

| Service | Default port | Note |
|---------|-----------------|------|
| Governed API | 8090 (or 1st free 8090-8099, see `.run/api.port`) | JSON API, **not** a web page |
| mock lab | 8082 | `GET /healthz` only |
| UX console | 5173 | **this is the graphical interface** |
| docker discovery-mock | 8081 | legacy lab |

The API has no root page: `GET /` returns `404 {"detail":"Not Found"}`, this is
normal. The useful routes are `/health`, `/actions/execute`, `/approvals`,
`/audit/...`, `/catalog/actions`, `/policies`. **The graphical UX is the console
on :5173**, not the API.

---

## 6. Configuration (R5 -- everything via env)

Override any default via an environment variable (defaults in
`cicd/lib/common.sh`):

| Variable | Default | Role |
|----------|--------|------|
| `INSPECT_IA_AGENTS_API_PORT` | 8090 | API port (otherwise auto-pick) |
| `INSPECT_IA_AGENTS_LAB_PORT` | 8082 | mock lab port |
| `INSPECT_IA_AGENTS_CONSOLE_PORT` | 5173 | console port |
| `INSPECT_IA_AGENTS_PLATFORM_DATA` | `<repo>/data` | event store directory |
| `INSPECT_IA_AGENTS_EVENT_STORE_PATH` | `<data>/inspect_ia_agents.events.db` | SQLite audit database |
| `INSPECT_IA_AGENTS_POLICIES_DIR` | `<repo>/config/policies` | policy versions |

Pid/logs/reports under `.run/`: `api.pid`, `api.port`, `lab.pid`,
`console.pid`, `*.log`, `campaigns/*.json`.

No secret is ever stored (R8) -- the credentials of real systems would come from
the environment, held by the proxies.

---

## 7. Links

- Installation (prerequisites + first start): [installation.md](installation.md)
- Platform (docker lab + e2e): [platform.md](platform.md)
- Track U API: [api.md](api.md)
- Catalog (initial plan of 118 actions, extended to 146): [../tracking/PLAN_high-risk-action-catalog_2026-06-12.md](../tracking/PLAN_high-risk-action-catalog_2026-06-12.md)
