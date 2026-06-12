# Plan : APEX --swarms -- Monaco flux analyzer (agent stream analysis window)

Date : 2026-06-13
Session : apex-20260613-flux-monaco
Status : EN_COURS (blocked at INIT: exec infra down -- npm install impossible)
Invariants concernes : I1 (read-only audit), I4 (seq ordering)
Depends on : PLAN_APEX_flux-tail-v2_2026-06-12.md (uses the bounded tail hook)

## Objectif

Add a Monaco-based analysis window for the agents' audit flux in the console:
inspect the live event stream as structured JSON (fold/search/highlight),
per-agent filtering, event detail view. Read-only viewer (the audit log is
immutable, I1); recette mode = blocking gates per react-recette.

## OBSERVE

- Monaco NOT in console/package.json -> new runtime dep `@monaco-editor/react`
  (+ `monaco-editor`). First runtime dependency beyond react/react-router:
  lazy-load the editor chunk so the base bundle stays small.
- Existing building blocks: useAuditTail v2 (bounded buffer, stalled,
  droppedCount), LogConsole, /audit/events (from_seq/tail/filters),
  /audit/export.jsonl.
- Backend: no new endpoint strictly required; analyzer feeds off the tail
  buffer + export link. Optional S4 below.

## THINK -- alternatives

- A (retenue) : new page `/flux` -- left: reused LogConsole tail (click line
  to select); right: Monaco read-only viewer showing either the selected
  event (JSON, folded) or the whole visible window as JSONL with follow mode.
  Pros: zero backend change to start, reuses tail hook + LogConsole, Monaco
  search/fold gives the analysis power asked. Cons: new dep (~2 MB chunk,
  lazy-loaded).
- B (rejetee) : embed Monaco pane inside the existing audit page. Rejected:
  audit page is table+filters oriented (forensic), mixing live tail + editor
  overloads it; separate page keeps both readable.
- C (rejetee) : no-dep viewer (pre + custom fold). Rejected: user explicitly
  asked Monaco; rebuilding fold/search is wasted effort.

## Sous-taches

- [ ] S0 INIT (BLOCKED, needs exec): `cd console && npm install @monaco-editor/react monaco-editor`
      then vite build green pre-flight. Also close cycle flux-tail-v2 gates
      (make gates, tsc, vitest) BEFORE building on top of it.
- [ ] S1 FluxAnalyzer component (`console/src/components/FluxAnalyzer.tsx`):
      lazy `React.lazy` Monaco wrapper, read-only, JSON language, dark theme
      consistent with LogConsole; props: events (AuditEvent[]), selectedSeq,
      mode "event"|"stream". R16: fixture = existing auditEvents.fixture.json;
      render-and-assert test with Monaco mocked (jsdom cannot run the real
      editor -- mock @monaco-editor/react with a textarea stub, assert the
      serialized JSON content + props).
- [ ] S2 page `/flux` (`console/src/pages/flux/index.tsx`): useAuditTail
      (agent filter select fed from listAgents), LogConsole on the left with
      line click -> select seq, FluxAnalyzer right, follow toggle, export
      button -> /audit/export.jsonl. Route + nav entry. Tests: render with
      fixture, click line -> analyzer shows that event JSON.
- [ ] S3 wiring polish: deep-link ?agent_id= and ?seq= (mirror audit page
      ?event_id= pattern), HelpModal entry if pattern exists for other pages.
- [ ] S4 (optional, only if needed during build) backend: GET /audit/events
      already covers needs; no change expected. Confirm during S2.
- [ ] S5 RECETTE (blocking): tsc, vite build (chunk-size check for lazy
      monaco), vitest run, make test + gates (no backend change expected ->
      regression only), runtime smoke if browser tooling available.

## Swarm usage

Code = sequential (git index races between writer agents already observed on
this repo). Swarm reserved for read-only phases: parallel review agents
(frontend lens, contract lens, perf lens) after S2, merged before S5.

## Decisions prises

- Monaco lazy-loaded, read-only (I1: nobody edits audit events).
- jsdom tests mock the editor module; real rendering checked at smoke stage.

## Ecarts et replanification

- 2026-06-13: INIT blocked -- exec infra (safety classifier) down; npm install
  and all gates impossible from the session. Plan written, build deferred.

## Resultat

(pending)
