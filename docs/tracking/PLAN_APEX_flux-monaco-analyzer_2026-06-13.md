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
- [x] S1 FluxAnalyzer component (`console/src/components/FluxAnalyzer.tsx`):
      WRITTEN 2026-06-13 (compile pending S0). + FluxAnalyzer.css + tests
      (pure fluxAnalyzerContent + mocked-editor render-and-assert).
      lazy `React.lazy` Monaco wrapper, read-only, JSON language, dark theme
      consistent with LogConsole; props: events (AuditEvent[]), selectedSeq,
      mode "event"|"stream". R16: fixture = existing auditEvents.fixture.json;
      render-and-assert test with Monaco mocked (jsdom cannot run the real
      editor -- mock @monaco-editor/react with a textarea stub, assert the
      serialized JSON content + props).
- [x] S2 page `/flux`: WRITTEN 2026-06-13 (compile pending S0). index.tsx +
      flux.css + index.test.tsx (5 cases incl. deep links); LogConsole gained
      onLineClick/selectedSeq (+ test); client gained auditExportUrl().
      Original spec: useAuditTail
      (agent filter select fed from listAgents), LogConsole on the left with
      line click -> select seq, FluxAnalyzer right, follow toggle, export
      button -> /audit/export.jsonl. Route + nav entry. Tests: render with
      fixture, click line -> analyzer shows that event JSON.
- [x] S3 wiring: route /flux + nav "Flux" in App.tsx; deep links ?agent_id=
      and ?seq= implemented in S2 directly. HelpModal entry: deferred to the
      PDCA pass (queued by user) with the rest of the polish.
- [ ] S4 (optional, only if needed during build) backend: GET /audit/events
      already covers needs; no change expected. Confirm during S2.
- [ ] S5 RECETTE (blocking): tsc, vite build (chunk-size check for lazy
      monaco), vitest run, make test + gates (no backend change expected ->
      regression only), runtime smoke if browser tooling available.

## Swarm usage

Code = sequential (git index races between writer agents already observed on
this repo). Swarm reserved for read-only phases: parallel review agents
(frontend lens, contract lens, perf lens) after S2, merged before S5.

## Swarm review (3 lenses, 2026-06-13) -- integrated

- BLOCKER fixed: @monaco-editor/react default loader pulls Monaco from a CDN
  -> new lazy module MonacoJsonViewer.tsx with loader.config({monaco}) +
  bundled editor/json workers (?worker imports). Offline lab safe.
- BLOCKER fixed: unbounded /audit/export.jsonl download link -> client-side
  Blob export of the visible window only; auditExportUrl removed.
- BLOCKER fixed: page tests ran the 1.5 s poll on real timers -> fake timers
  + flush() helper across the suite.
- MAJOR fixed: selection state duplicated URL -> selectedSeq now DERIVED from
  ?seq= (back/forward coherent). Stream value throttled (2 s) against editor
  model resets. Clickable lines: role=button + tabIndex + keyboard handler.
  listAgents mock now uses the real captured agents fixture (R16).
- MINOR fixed: canonical key order in JSONL, empty-stream hint, ErrorBoundary
  around the lazy editor, fallback min-height, controlled select placeholder
  while agents load, --badge-red-fg var, autoscroll on same-length eviction.
- Rejected findings (verified false): approval_state guard already correct;
  Resume label exact-match concern; monaco mock default-export shape.
- DEFERRED to PDCA: jsdom/vite CVE upgrades (R17, needs npm exec);
  payload display documented as intentional (audit audience).

## Decisions prises

- Monaco lazy-loaded, read-only (I1: nobody edits audit events).
- jsdom tests mock the lazy viewer module; real rendering checked at smoke stage.
- Mode (event/stream) is ephemeral UI state, NOT in the URL (documented).

## Ecarts et replanification

- 2026-06-13: INIT blocked -- exec infra (safety classifier) down; npm install
  and all gates impossible from the session. Plan written, build deferred.

## Resultat

(pending)
