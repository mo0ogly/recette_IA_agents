# TODO -- reuse backlog from microsoft/agent-framework + langwatch/scenario

Deferred items from the reuse analysis (2026-06-13). The MCP discovery surface is
being implemented now via APEX; everything below is queued.

## High value
- [ ] **OpenTelemetry audit semantics** -- adopt OTel semantic conventions for the
      action log / audit trace so AgentRail traces are interoperable with any OTel
      backend. Audit Plane (I1). Effort: medium.
- [ ] **RedTeamAgent -> negative-corpus generator** -- transpose scenario's RedTeamAgent
      to auto-generate adversarial subjects (rag-poisoning, capability_overreach).
      Effort: medium.
- [ ] **require_approval -> real approval workflow** -- a MAF approval=always action
      triggers an actual approval workflow (not just a judged flag). Closes I6 loop.
      Effort: medium.

## Medium value
- [ ] **Per-turn assertions in simulate** -- extend recette/simulate.py to assert at any
      conversation point, not only the final verdict (scenario feature). Effort: quick win.
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
