# Plan : APEX -- flux listening tool v2 (audit tail + LogConsole)

Date : 2026-06-12
Session : apex-20260612-flux-tail-v2
Status : EN_COURS
Invariants concernes : I1 (read-only audit endpoints), I4 (deterministic ordering by seq)

## Objectif

Harden and extend the live flux listening tool of the console: the `useAuditTail`
polling hook + the reusable `LogConsole` window (consumers: cockpit, verdicts;
sibling tail in servers page). Address the health-scan findings below without
changing the polling transport.

## OBSERVE -- health scan

- H1 `useAuditTail` accumulates events without bound (memory + render cost on long sessions).
- H2 First poll fetches the FULL history (`from_seq=0`, no limit) -- heavy on a large store.
- H3 Poll errors are swallowed silently (`catch {}`): a dead backend looks like a quiet log.
- H4 `LogConsole` renders every line, no cap (mitigated by H1 fix).
- H5 Pause gives no signal of how many lines arrived while paused.
- H6 No per-level (info/warn/error) filter, only substring.
- H7 `ServerLogPanel` (servers page) duplicates the tail loop (DRY debt -- out of scope, noted).
- H8 Cursor/events not reset when hook filters change (latent: current consumers pass none).

## THINK -- alternatives

- A (retenue) : keep polling transport; add backend `tail=N` backfill param
  (read-only, composes with filters), bound the hook buffer (`maxEvents`,
  dropped counter), expose a `stalled` status after consecutive failures,
  reset cursor+buffer on filter change; LogConsole gains level filter,
  paused "+N" badge, stalled badge, dropped notice. Pros: small risk, no new
  dependency, no transport change, every finding addressed. Cons: latency
  stays at poll interval.
- B (rejetee) : switch to SSE (`text/event-stream` + EventSource). Real push
  but new server path, harder unit tests, no need at lab cadence (1.5 s poll).
- C (rejetee) : virtualized list (react-window). New runtime dependency
  against the repo zero-dep stance; bounded buffer suffices at lab scale.

## Sous-taches

- [ ] S1 backend `tail` param on GET /audit/events -- last N matching events
      after filters, ordered by seq; mutually exclusive with from_seq>0 use
      kept sane (tail applies to the filtered set). Files:
      recette/api/routers/audit.py, tests/test_api_platform.py.
      Success: unittest green, gates green. Pipeline: PYTHON.
- [ ] S2 hook v2 -- options {maxEvents (default 2000), intervalMs}; initial
      backfill via tail=maxEvents; bounded buffer + droppedCount; stalled
      status after 3 consecutive failures (clears on success); cursor+buffer
      reset when agentId/targetSystem/kind change. Files:
      console/src/hooks/useAuditTail.ts, useAuditTail.test.ts,
      console/src/api/client.ts (tail param). Success: vitest green, tsc clean.
      Pipeline: REACT.
- [ ] S3 LogConsole UX -- level filter (all/info/warn/error), "+N new" badge
      while paused, optional stalled badge prop, dropped-lines notice prop.
      Files: LogConsole.tsx, LogConsole.css, LogConsole.test.tsx.
      Success: vitest green. Pipeline: REACT.
- [ ] S4 wire consumers -- cockpit + verdicts pass stalled/dropped to
      LogConsole. Files: pages/cockpit/index.tsx, pages/verdicts/index.tsx
      (+ their tests if assertions shift). Success: vitest green, tsc clean.
      Pipeline: REACT.
- [ ] S5 RECETTE -- python -m unittest, make gates, tsc --noEmit, vite build,
      vitest run; regression vs pre-flight baseline.

## Decisions prises

- Alternative A selected (see THINK). B/C rejected: transport churn and a new
  dependency are not justified by lab-scale needs.

## Ecarts et replanification

(none yet)

## Resultat

(pending)
