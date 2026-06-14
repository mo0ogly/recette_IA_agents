# inspect_ia_agents console -- discovery-recette cockpit (UX)

React + Vite + TypeScript cockpit for the inspect_ia_agents **recette** platform.

This console is NOT the discovery tool. It is the bench that **produces the
test subjects** the discovery / identification tools must detect and judge:
configure agents, launch / stop them (mock or real AI), run campaigns, replay
recordings, and score the tools under test against the ground-truth corpus.

It talks to the API directly (raw JSON, no envelope). Base URL from
`VITE_INSPECT_IA_AGENTS_API_URL` (R5).

## Tabs

| Tab | Route | Purpose | API |
|-----|-------|---------|-----|
| **Tableau de bord** | `/dashboard` | control board: per-agent live status, the two mock/real axes (AI, target), launch/stop | `GET /runs` (poll), `POST /runs` |
| **Cockpit** | `/cockpit` | pick an agent, choose mock (scripted stub) or real AI (bound ai_backend), launch, watch the live action stream, stop | `POST /runs` (kind=lane_b), `/runs/{id}/ws`, `/runs/{id}/stop` |
| **Recette** | `/recette` | run the discovery and identification recettes over the corpus; per-surface / per-agent scorecard vs ground-truth | `POST /runs` (kind=discovery\|identification) |
| **Campagnes** | `/campaigns` | persisted agent sets run on demand; live frames; list recordings; **replay** with an IDENTIQUE/DIVERGENT determinism verdict (I4) | `/campaigns*`, `/recordings*` |
| **Agents** | `/agents` | define each agent (principal, target_system, goal, capability_scope as canonical actions, bound ai_backend) + **AI-backend CRUD** (provider+model, no secret, R8) | `/config/agents`, `/config/ai-backends` |
| **Serveurs** | `/servers` | server registry (mock_local / declared_url / real_saas): CRUD, start/stop of managed lab servers, live status, JSONL access-log tail | `/config/servers*` |
| Catalog | `/catalog` | governance mock: 118-action catalog + policy editor | `/catalog/actions`, `/policies` |
| Approvals | `/approvals` | governance mock: approval inbox (I6) | `/approvals*` |
| Audit | `/audit` | governance mock: immutable event log + hash chain | `/audit/*` |

The `Gouvernance (mock)` group (Catalog / Approvals / Audit) is a secondary
governance-platform UI kept for triage; it is not the recette path.

Every tab has a detailed `? Aide` help modal explaining what it governs and the
invariants it enforces.

## Mock vs real AI

- **Mock**: a scripted stub of decisions (`{kind, tool_name, tool_args, text}`),
  deterministic, zero key, zero side effect. Ideal for stable recette campaigns.
- **Real AI**: the agent's bound `ai_backend` (provider + model) drives a live
  LLM; the provider key is resolved from the environment (R8), never stored.

`capability_scope` is the set of **canonical actions** the agent may call
(`read_repo, list_repos, read_ci, open_issue, comment_issue, open_pr, merge_pr,
push, manage_webhook, manage_release, trigger_ci`), not a system name.

## Replay (I4)

Running a campaign persists one recording per step. Replaying a recording
re-issues its exact decisions and compares the resulting action log to the
original: `IDENTIQUE` proves determinism, `DIVERGENT` flags a non-deterministic
source to fix.

## Run

From the repo root (wires the API URL automatically, auto-picks a free port):

```
./recette.sh platform up
./recette.sh console start      # http://localhost:5173
```

Or directly:

```
npm install
VITE_INSPECT_IA_AGENTS_API_URL=http://localhost:8090 npm run dev
```

Default API base `http://localhost:8080`. When started via `recette.sh`, the
resolved API port is in `.run/api.port` (it auto-shifts if 8090 is taken).

## Checks

```
npx tsc --noEmit
npx vitest run
npm run build
```

Page fixtures under `src/pages/*/__fixtures__/` are captured from the real
backend, not hand-written (R16 frontend contract gate). See
[../docs/runbooks/recette-sh.md](../docs/runbooks/recette-sh.md) for the full
operator guide and [../docs/runbooks/platform.md](../docs/runbooks/platform.md)
for the API and run model.
