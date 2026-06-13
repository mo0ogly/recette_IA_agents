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
- [ ] **Run cache for real-mode** -- cache reproducible real-mode LLM runs (cost +
      determinism); overlaps ReplayLlm/recording. Effort: medium.
- [ ] **Multi-agent handoff scenarios** -- subjects where agent A delegates to B
      (MAF orchestration: sequential/concurrent/handoff). Effort: medium.

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
