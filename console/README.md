# AgentRail console (UX)

React + Vite + TypeScript console for the governed-execution platform. Four
pages, talking directly to the API (raw JSON, no envelope):

| Page | Route | Purpose |
|------|-------|---------|
| Agents | `/agents` | configure the AI behind each agent: model, system prompt, capability scope, role, AI backend |
| Catalog | `/catalog` | browse the 118-action catalog; edit policy rules and publish/activate a new policy version |
| Approvals | `/approvals` | approval inbox (I6): approve / deny pending actions, sweep timeouts |
| Audit | `/audit` | immutable event log, hash-chain status, filters, payload inspection |

## Run

From the repo root (recommended -- wires the API URL automatically):

```
./recette.sh platform up
./recette.sh console start      # http://localhost:5173
```

Or directly:

```
npm install
VITE_AGENTRAIL_API_URL=http://localhost:8090 npm run dev
```

The API base URL comes from `VITE_AGENTRAIL_API_URL` (R5), default
`http://localhost:8080`. Set it to the running API port (see `.run/api.port`
when started via `recette.sh`, since the port auto-shifts if 8090 is taken).

## Checks

```
npx tsc --noEmit
npx vitest run
npm run build
```

Test fixtures under `src/pages/*/__fixtures__/` are captured from the real
backend, not hand-written (R16 frontend contract gate). See
[../docs/runbooks/recette-sh.md](../docs/runbooks/recette-sh.md) for the full
operator guide.
