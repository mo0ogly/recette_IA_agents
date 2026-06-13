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
- [ ] MCP discovery surface -- IN PROGRESS (APEX)
