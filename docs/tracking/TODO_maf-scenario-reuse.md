# TODO -- reuse backlog from microsoft/agent-framework + langwatch/scenario

Deferred items from the reuse analysis (2026-06-13). The MCP discovery surface is
being implemented now via APEX; everything below is queued.

## High value
- [ ] **OpenTelemetry audit semantics** -- adopt OTel semantic conventions for the
      action log / audit trace so AgentRail traces are interoperable with any OTel
      backend. Audit Plane (I1). Effort: medium.
- [x] **RedTeamAgent -> negative-corpus generator** -- DONE. recette/redteam.py:
      RedTeamSimulator (Crescendo 4-phase adversarial user, grounded on
      scenario/red_team_agent.py) + to_corpus_subject (deterministic single-axis
      negative freeze, ground-truth derived from judge_subject). tests/test_redteam.py.
- [x] **require_approval -> real approval workflow** -- DONE. A MAF gated tool
      (mcp invoke_tool / handoff) is wired onto the EXISTING I6 pipeline via a new
      catalog domain recette/platform/catalog/domains/mcp.py (escalate-class,
      deny-by-default): gateway escalate -> pending -> ApprovalService -> console
      Approvals page (surfaces automatically). Cascade: lab domain + coverage +
      role-matrix (tool_operator) regenerated. tests/test_maf_approval_workflow.py
      (real gateway: escalate/pending/approve/deny/timeout, no auto-approve) +
      console R16 contract test on the existing Approvals page.

## Medium value
- [x] **Per-turn assertions in simulate** -- DONE. recette/simulate.py: SimCheck /
      SimState / CheckResult, run after each turn (grounded on scenario's ScriptStep
      Callable[[ScenarioState], Optional[ScenarioResult]]); a failing check halts.
- [ ] **Frontend red-team/simulation view** -- DEFERRED (own cycle): needs a
      result-persistence layer + endpoint; red-team/sim output is LLM-driven
      (non-deterministic), not a clean recette endpoint. Do not bolt on.
- [x] **Run cache for real-mode** -- DONE for orchestration via recette/orchestrate.py:
      OrchestrationRecording persists the team + ordered LLM decisions + the run;
      replay() re-drives with ReplayLlm and reproduces the EXACT run (I4). The Lane B
      single-agent path already had recette/recording.py. (Generalised LLM HTTP-level
      response cache across all runners remains a possible future optimisation.)
- [x] **Multi-agent handoff scenarios** -- DONE. The judged unit is a TEAM:
      recette/maf_orchestration.py (judge_orchestration, grounded on the real MAF
      HandoffBuilder/HandoffConfiguration + unknown-target rule + termination,
      deterministic I4) + maf_orchestration_harness.py + two schemas
      (maf-orchestration[-run]) + corpus/maf_orchestration/ (1 correct + 4 mono-axis
      negatives) + report/subjects/CLI wiring + console Discovery row +
      tests/test_maf_orchestration.py (4 dims, single-axis orthogonality,
      determinism). Sequential + concurrent styles ALSO done: team.style
      discriminator (handoff|sequential|concurrent), run.order, style-aware judge
      branches grounded on SequentialBuilder (ordered chain, each once) and
      ConcurrentBuilder (fan-out, each once); corpus 9 teams; console Corpus
      browser page over GET /subjects. group_chat style ALSO done (GroupChatBuilder:
      bounded turns, no monopoly; 11 teams total) plus an end-to-end live -> record
      -> replay -> freeze pipeline (recette/orchestrate.py, CLI `recette orchestrate`,
      scripts/run_orchestration_live_groq.py, docs/runbooks/orchestration-recette.md).
      magentic (manager/ledger) style remains future.

## Platform territory (heavier)
- [ ] **Middleware pipeline pattern** for the Gateway mediation (I2) -- reference pattern.
- [ ] **Checkpointing / time-travel** semantics aligned with replay (I4).
- [ ] **DevUI**-style interactive trace viewer in the console -- reference UX.
- [ ] **AF Labs benchmark/RL eval** harness as a scorecard benchmark reference.

## Done
- [x] MAF declarative spec -> unified manifest (import-maf)
- [x] UserSimulatorAgent -> recette/simulate.py
- [x] JudgeAgent -> recette/judge.py (judge_subject)
- [x] require_approval -> approval gate judged (I6)
- [x] MCP discovery surface -- DONE (catalog domain mcp + .agentrail manifest scan)

---

## Full repo audit (2026-06-13) -- remaining reusable ideas, ranked

Exhaustive sweep of both repos' module trees vs what we have. Each item cites the
REAL source file to ground a future cycle on (rule: reprends le code des repos).
Ordered by recette value. Apply with APEX (corpus + judge + tests + doc + help).

### High value
- [x] **magentic orchestration style** -- DONE. team.style "magentic"; judged unit =
      team; behavior = bounded rounds + no stall (same speaker selected >= 3 in a
      row = MAF max_stall_count); capabilities = membership (invalid next_speaker).
      _check_behavior_magentic in recette/maf_orchestration.py; drive() routes it to
      the manager-routed loop (orchestrate.py); corpus magentic-research (1 correct +
      1 stall negative); tests + docs + Help. Five MAF styles complete (13 teams).
      Grounded on _magentic.py (StandardMagenticManager, progress ledger next_speaker).
- [x] **OpenTelemetry audit semantics** -- DONE. recette/otel.py maps an
      orchestration run/recording to canonical OTel GenAI spans (invoke_agent /
      execute_tool, gen_ai.provider.name/.request.model/.agent.name/.tool.name),
      grounded on the REAL agent_framework/observability.py (NOT _telemetry.py,
      which is only user-agent). Dependency-free + deterministic (I4: digest ids,
      logical times) + read-only (I1). to_otlp() -> OTLP/JSON ResourceSpans for any
      OTel backend; CLI `recette orchestrate otel <recording>`; tests/test_otel.py;
      mermaid in docs/runbooks/replay-model.md. A real OTel SDK export stays an
      optional [otel] extra. (Mapping the git/MAF AgentActionEvent action log to
      spans too remains a small follow-up.)

### Medium value
- [ ] **Generic real-mode run cache** -- a content-addressed cache of LLM calls
      keyed by (system, history, tools) so a live run is cheap + reproducible across
      ALL runners (not just orchestration/campaign recordings). Source:
      `scenario/cache.py` (langwatch). Overlaps ReplayLlm; this is the call-level
      cache layer under build_llm. Effort: medium.
- [ ] **Auto workflow viz** -- generate the mermaid we now hand-write from a team /
      campaign definition. Source: `python/packages/core/agent_framework/_workflows/_viz.py`.
      A `recette orchestrate viz <team>` that prints a mermaid graph. Effort: small.
- [ ] **pytest plugin** -- expose the recette corpus as pytest test cases (parametrised
      per subject) alongside the unittest suite. Source: `scenario/pytest_plugin.py`.
      Effort: small. Optional (unittest already green).
- [ ] **Record the live campaign/role-matrix/rag runners** -- the scripts/run_*_live_groq.py
      family still throws the live LLM run away ("NOT a replayable recette"). Capture
      their decisions exactly like recette/orchestrate.py so each becomes replayable.
      Effort: medium.

### Platform territory (heavier -- reference patterns, not recette-core)
- [ ] **Middleware pipeline pattern** for the Gateway mediation (I2). Source:
      `python/packages/core/agent_framework/_middleware.py`.
- [ ] **Checkpointing / time-travel** (resume a run mid-flight), aligned with replay (I4).
      Source: `python/packages/core/agent_framework/_workflows/_checkpoint.py` + `_state.py`.
- [ ] **DevUI-style interactive trace/replay viewer** in the console. Source:
      `python/packages/devui/agent_framework_devui/` -- our analog: a console page that
      loads an OrchestrationRecording/CampaignRecording and steps through it.
- [ ] **AF Labs benchmark/eval harness** as a scorecard benchmark reference. Source:
      `python/packages/core/agent_framework/lab/` + core `_evaluation.py`.

### Deliberately NOT applicable (do not import -- documented so we stop re-litigating)
- MAF `_mcp.py` runtime (139KB), `_harness/` (agent runtime: loop/memory/todo/
  background), `_sessions.py`/`_compaction.py` (conversation memory), hosting adapters
  (azurefunctions/copilotstudio/chatkit), `ag_ui/`, and the LangWatch SaaS dashboard
  are agent-RUNTIME or deployment concerns, not recette. Importing them breaks I4
  (non-determinism in the decision path) or is out of scope. The recette models their
  CONTRACT (capability_scope, tool_kind, approval), never their runtime.
