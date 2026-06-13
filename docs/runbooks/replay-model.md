# The unified replay model -- agents, teams, campaigns

Every recette subject in AgentRail follows the same record / replay / freeze
shape, so a non-deterministic live run (a real LLM, real verdicts) becomes a
deterministic, persistent artifact you can replay "pour voir ce que ca fait" and,
once vetted, freeze into the corpus. The judge / gateway stays deterministic
(I4); all non-determinism is captured once, at record time.

## Three subject kinds, one pattern

```mermaid
flowchart LR
  subgraph LIVE["Live run (non-deterministic)"]
    L1["Lane B agent\nrun_agent + LlmBackend"]
    L2["Orchestration team\ndrive(team, LlmBackend)"]
    L3["Campaign\nCampaignRunner.run(doc)"]
  end
  subgraph REC["Record (persistent artifact, gitignorable)"]
    R1["recette/recording.py\nRecording (decisions + actions)"]
    R2["recette/orchestrate.py\nOrchestrationRecording (decisions + run)"]
    R3["recette/campaign.py\nCampaignRecording (doc + verdicts)"]
  end
  subgraph REPLAY["Replay (deterministic, I4)"]
    P1["ReplayLlm -> same action log"]
    P2["ReplayLlm -> same run -> judge"]
    P3["re-submit doc -> same verdicts"]
  end
  subgraph FREEZE["Freeze (corpus subject)"]
    F1["promote.freeze_recording\ncorpus/agents/correct"]
    F2["orchestrate.freeze_to_corpus\ncorpus/maf_orchestration"]
    F3["the campaign JSON is already\nits own deterministic record"]
  end
  L1 --> R1 --> P1 --> F1
  L2 --> R2 --> P2 --> F2
  L3 --> R3 --> P3 --> F3
```

## Where the non-determinism lives, and how it is captured

```mermaid
flowchart TD
  subgraph PURE["Deterministic core (I4) -- pure functions"]
    J1["judge_orchestration(team, run)"]
    J2["gateway decide(event, policy, catalog)"]
  end
  subgraph CAPTURED["Captured at record time"]
    C1["LLM decisions (tool_call / final)"]
  end
  LLM["Live LLM (Groq, ...)"] -- "non-deterministic" --> C1
  C1 -- "stored in the recording" --> RPL["ReplayLlm replays decisions in order"]
  RPL --> J1
  RPL --> J2
  J1 --> V["verdict (always identical on replay)"]
  J2 --> V
```

## Orchestration: drive -> record -> replay -> freeze

```mermaid
sequenceDiagram
  participant Op as Operator
  participant Drv as drive(team, backend)
  participant LLM as LlmBackend (Groq/Stub)
  participant Rec as OrchestrationRecording
  participant Judge as judge_orchestration (pure)

  Op->>Drv: record(team, GroqLlm)
  loop until final / max_steps
    Drv->>LLM: decide(system, history, tools)
    LLM-->>Drv: LlmDecision (handoff_to_X / use_tool / speak_Y / final)
    Drv->>Drv: emit hop / order-entry / tool call
  end
  Drv-->>Rec: team + ordered decisions + run
  Op->>Rec: save(path)  %% persistent

  Op->>Drv: replay(recording)
  Drv->>LLM: ReplayLlm(decisions).decide(...)
  LLM-->>Drv: the recorded decision (in order)
  Drv->>Drv: reproduce the EXACT run (integrity guard)
  Drv->>Judge: judge_orchestration(team, run)
  Judge-->>Op: verdict (identical every replay, I4)
```

## The four orchestration styles (grounded on the real MAF builders)

```mermaid
flowchart TB
  subgraph handoff["handoff -- HandoffBuilder"]
    H0["start_agent"] --> H1["agent A"]
    H1 -- "handoff_to (declared edge)" --> H2["agent B"]
    H2 -- "handoff_to" --> H1
  end
  subgraph sequential["sequential -- SequentialBuilder"]
    S1["p1"] --> S2["p2"] --> S3["p3 (terminator)"]
  end
  subgraph concurrent["concurrent -- ConcurrentBuilder"]
    D["dispatch"] --> N1["p1"]
    D --> N2["p2"]
    D --> N3["p3"]
    N1 --> AG["aggregate (participant order)"]
    N2 --> AG
    N3 --> AG
  end
  subgraph group_chat["group_chat -- GroupChatBuilder"]
    M["manager"] -- "speak_X" --> T1["turn: responder"]
    M -- "speak_Y" --> T2["turn: analyst"]
    M -- "speak_X" --> T3["turn: responder"]
  end
  subgraph magentic["magentic -- MagenticBuilder"]
    MM["manager + progress ledger"] -- "next_speaker" --> R1["round: planner"]
    MM -- "next_speaker" --> R2["round: researcher"]
    MM -- "next_speaker" --> R3["round: writer"]
  end
```

Behavior axis per style: handoff = start at start_agent, within the termination
bound, no loop; sequential = executed order == declared order, each once;
concurrent = each declared participant once; group_chat = bounded turns, no
participant monopolises; magentic = bounded rounds, no stall (same speaker
selected three rounds in a row).

## Campaign record -> replay (I4 at the campaign level)

A campaign of scripted actions is already deterministic (the gateway decision is
a pure function of event + policy + catalog). Recording captures the verdict
sequence; replay re-submits the same document and asserts the verdicts reproduce.

```mermaid
sequenceDiagram
  participant Op as Operator
  participant Run as CampaignRunner
  participant GW as Gateway API (deterministic)
  participant Rec as CampaignRecording

  Op->>Run: record_campaign(doc)
  loop each action
    Run->>GW: POST /actions/execute
    GW-->>Run: verdict (allow/deny/escalate)
  end
  Run-->>Rec: doc + verdict sequence
  Op->>Rec: save(rec.json)

  Op->>Run: replay_campaign(recording)
  loop each action
    Run->>GW: POST /actions/execute (same doc)
    GW-->>Run: verdict
  end
  Run->>Run: compare to recorded verdicts
  Run-->>Op: deterministic = True/False
```

CLI:

```
python3 -m recette.campaign record campaigns/identity-offboarding.campaign.json --out /tmp/c.json
python3 -m recette.campaign replay /tmp/c.json
```

Live, LLM-driven campaign demos (`scripts/run_*_live_groq.py`) are the
non-deterministic counterpart: to make one replayable, record the live LLM
decisions exactly as `recette/orchestrate.py` does and replay them through the
same governed gateway -- the same record / replay / freeze pattern as above.

## Secrets at record time (R18)

```mermaid
flowchart LR
  A["build_llm('groq', model)"] --> B{key resolved?}
  B -- "per-backend store" --> S1["data/backend_secrets.json"]
  B -- "env fallback" --> S2[".env -> GROQ_API_KEY"]
  S1 --> OK["LLM call"]
  S2 --> OK
  B -- "none found" --> ERR["error: ask operator to fill .env\n(never paste in chat, never hardcode)"]
```

See `.claude/rules/secrets-source-of-truth.md` (R18) and
`docs/runbooks/orchestration-recette.md`.

## OpenTelemetry GenAI export (audit interop, I1/I4)

A recording exports to OpenTelemetry GenAI spans so an AgentRail audit trail
interoperates with any OTel backend. The attribute/operation names are the
canonical GenAI semantic conventions taken from the real
`agent_framework/observability.py` (`invoke_agent` / `execute_tool`,
`gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.agent.name`,
`gen_ai.tool.name`). Dependency-free and deterministic (I4): span/trace ids are a
stable digest of the run, timestamps are logical (no wall clock), so the same run
exports byte-identical spans; the recording is read-only (I1).

```mermaid
flowchart TD
  REC["OrchestrationRecording (team + run)"] --> RT["root span: invoke_agent {team}"]
  RT --> A1["invoke_agent {participant}\ngen_ai.agent.name / .provider.name / .request.model"]
  RT --> A2["invoke_agent {participant}"]
  RT --> T1["execute_tool {tool}\ngen_ai.tool.name / .tool.call.id"]
  RT --> OTLP["to_otlp() -> ResourceSpans (OTLP/JSON)"]
  A1 --> OTLP
  A2 --> OTLP
  T1 --> OTLP
  OTLP --> BE["any OTel backend / collector"]
```

```
python3 -m recette orchestrate otel /tmp/run.json --out spans.json
```

`recette/otel.py`: `orchestration_spans(team, run)` -> `to_otlp(spans)`. A real
OTel exporter (optional `[otel]` extra) re-stamps wall-clock times at emit; the
recette only guarantees the structure is reproducible.
