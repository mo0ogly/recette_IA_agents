# Le modele de replay unifie -- agents, equipes, campagnes

Chaque sujet de recette dans inspect_ia_agents suit la meme forme record / replay /
freeze, de sorte qu'une execution live non deterministe (un vrai LLM, de vrais
verdicts) devient un artefact deterministe et persistant que l'on peut rejouer
"pour voir ce que ca fait" puis, une fois valide, figer dans le corpus. Le juge /
la gateway reste deterministe (I4) ; tout le non-determinisme est capture une seule
fois, au moment de l'enregistrement.

## Trois sortes de sujets, un seul pattern

```mermaid
flowchart LR
  subgraph LIVE["Execution live (non deterministe)"]
    L1["Agent Lane B\nrun_agent + LlmBackend"]
    L2["Equipe d'orchestration\ndrive(team, LlmBackend)"]
    L3["Campagne\nCampaignRunner.run(doc)"]
  end
  subgraph REC["Record (artefact persistant, gitignorable)"]
    R1["recette/recording.py\nRecording (decisions + actions)"]
    R2["recette/orchestrate.py\nOrchestrationRecording (decisions + run)"]
    R3["recette/campaign.py\nCampaignRecording (doc + verdicts)"]
  end
  subgraph REPLAY["Replay (deterministe, I4)"]
    P1["ReplayLlm -> meme journal d'actions"]
    P2["ReplayLlm -> meme run -> juge"]
    P3["resoumettre le doc -> memes verdicts"]
  end
  subgraph FREEZE["Freeze (sujet du corpus)"]
    F1["promote.freeze_recording\ncorpus/agents/correct"]
    F2["orchestrate.freeze_to_corpus\ncorpus/maf_orchestration"]
    F3["le JSON de la campagne est deja\nson propre enregistrement deterministe"]
  end
  L1 --> R1 --> P1 --> F1
  L2 --> R2 --> P2 --> F2
  L3 --> R3 --> P3 --> F3
```

## Ou vit le non-determinisme, et comment il est capture

```mermaid
flowchart TD
  subgraph PURE["Coeur deterministe (I4) -- fonctions pures"]
    J1["judge_orchestration(team, run)"]
    J2["gateway decide(event, policy, catalog)"]
  end
  subgraph CAPTURED["Capture au moment de l'enregistrement"]
    C1["Decisions LLM (tool_call / final)"]
  end
  LLM["LLM live (Groq, ...)"] -- "non deterministe" --> C1
  C1 -- "stocke dans l'enregistrement" --> RPL["ReplayLlm rejoue les decisions dans l'ordre"]
  RPL --> J1
  RPL --> J2
  J1 --> V["verdict (toujours identique au replay)"]
  J2 --> V
```

## Orchestration : drive -> record -> replay -> freeze

```mermaid
sequenceDiagram
  participant Op as Operateur
  participant Drv as drive(team, backend)
  participant LLM as LlmBackend (Groq/Stub)
  participant Rec as OrchestrationRecording
  participant Judge as judge_orchestration (pur)

  Op->>Drv: record(team, GroqLlm)
  loop jusqu'a final / max_steps
    Drv->>LLM: decide(system, history, tools)
    LLM-->>Drv: LlmDecision (handoff_to_X / use_tool / speak_Y / final)
    Drv->>Drv: emet hop / order-entry / appel d'outil
  end
  Drv-->>Rec: team + decisions ordonnees + run
  Op->>Rec: save(path)  %% persistant

  Op->>Drv: replay(recording)
  Drv->>LLM: ReplayLlm(decisions).decide(...)
  LLM-->>Drv: la decision enregistree (dans l'ordre)
  Drv->>Drv: reproduit le run EXACT (garde d'integrite)
  Drv->>Judge: judge_orchestration(team, run)
  Judge-->>Op: verdict (identique a chaque replay, I4)
```

## Les quatre styles d'orchestration (ancres sur les vrais builders MAF)

```mermaid
flowchart TB
  subgraph handoff["handoff -- HandoffBuilder"]
    H0["start_agent"] --> H1["agent A"]
    H1 -- "handoff_to (arete declaree)" --> H2["agent B"]
    H2 -- "handoff_to" --> H1
  end
  subgraph sequential["sequential -- SequentialBuilder"]
    S1["p1"] --> S2["p2"] --> S3["p3 (terminateur)"]
  end
  subgraph concurrent["concurrent -- ConcurrentBuilder"]
    D["dispatch"] --> N1["p1"]
    D --> N2["p2"]
    D --> N3["p3"]
    N1 --> AG["agregation (ordre des participants)"]
    N2 --> AG
    N3 --> AG
  end
  subgraph group_chat["group_chat -- GroupChatBuilder"]
    M["manager"] -- "speak_X" --> T1["tour : responder"]
    M -- "speak_Y" --> T2["tour : analyst"]
    M -- "speak_X" --> T3["tour : responder"]
  end
  subgraph magentic["magentic -- MagenticBuilder"]
    MM["manager + registre de progression"] -- "next_speaker" --> R1["round : planner"]
    MM -- "next_speaker" --> R2["round : researcher"]
    MM -- "next_speaker" --> R3["round : writer"]
  end
```

Axe comportement par style : handoff = demarrer a start_agent, dans la borne de
terminaison, sans boucle ; sequential = ordre d'execution == ordre declare,
chacun une fois ; concurrent = chaque participant declare une fois ; group_chat =
tours bornes, aucun participant ne monopolise ; magentic = rounds bornes, pas de
blocage (le meme locuteur selectionne trois rounds d'affilee).

## Enregistrement de campagne -> replay (I4 au niveau campagne)

Une campagne d'actions scriptees est deja deterministe (la decision de la gateway
est une fonction pure de event + policy + catalog). L'enregistrement capture la
sequence de verdicts ; le replay resoumet le meme document et asserte que les
verdicts se reproduisent.

```mermaid
sequenceDiagram
  participant Op as Operateur
  participant Run as CampaignRunner
  participant GW as API Gateway (deterministe)
  participant Rec as CampaignRecording

  Op->>Run: record_campaign(doc)
  loop chaque action
    Run->>GW: POST /actions/execute
    GW-->>Run: verdict (allow/deny/escalate)
  end
  Run-->>Rec: doc + sequence de verdicts
  Op->>Rec: save(rec.json)

  Op->>Run: replay_campaign(recording)
  loop chaque action
    Run->>GW: POST /actions/execute (meme doc)
    GW-->>Run: verdict
  end
  Run->>Run: compare aux verdicts enregistres
  Run-->>Op: deterministe = True/False
```

CLI :

```
python3 -m recette.campaign record campaigns/identity-offboarding.campaign.json --out /tmp/c.json
python3 -m recette.campaign replay /tmp/c.json
```

Les demos de campagne live pilotees par LLM (`scripts/run_*_live_groq.py`) sont la
contrepartie non deterministe : pour rendre l'une d'elles rejouable, enregistrer
les decisions du LLM live exactement comme le fait `recette/orchestrate.py` et les
rejouer a travers la meme gateway gouvernee -- le meme pattern record / replay /
freeze que ci-dessus.

## Secrets au moment de l'enregistrement (R18)

```mermaid
flowchart LR
  A["build_llm('groq', model)"] --> B{cle resolue ?}
  B -- "store par backend" --> S1["data/backend_secrets.json"]
  B -- "fallback env" --> S2[".env -> GROQ_API_KEY"]
  S1 --> OK["appel LLM"]
  S2 --> OK
  B -- "aucune trouvee" --> ERR["erreur : demander a l'operateur de remplir .env\n(ne jamais coller dans le chat, ne jamais coder en dur)"]
```

Voir `.claude/rules/secrets-source-of-truth.md` (R18) et
`docs/runbooks/orchestration-recette.md`.

## Checkpoint / voyage dans le temps (I4)

Parce que `drive` est une fonction pure du flux de decisions, un run peut etre fige
a n'importe quelle etape et repris -- pour reproduire le chemin original ou pour
bifurquer vers un autre. `recette/checkpoint.py` : `checkpoint(recording, after=k)`
fige les k premieres decisions ; `resume(cp, tail)` rejoue le prefixe puis continue
avec `tail` (un `ReplayLlm` du tail original reproduit le run ; un backend live ou
different bifurque) ; `partial_run(cp)` est le run tronque au checkpoint. Reflete
le concept de `_workflows/_checkpoint.py` de l'agent-framework, garde sans
dependance et deterministe.

```mermaid
flowchart LR
  REC["recording (decisions 0..N)"] --> CP["checkpoint(after=k)\nprefixe 0..k"]
  CP --> R1["resume(cp, ReplayLlm(tail)) -> chemin original"]
  CP --> R2["resume(cp, live/autre) -> chemin bifurque"]
  CP --> PR["partial_run(cp) -> prefixe seulement"]
```

## Export OpenTelemetry GenAI (interop d'audit, I1/I4)

Un enregistrement s'exporte vers des spans OpenTelemetry GenAI afin qu'une piste
d'audit inspect_ia_agents interopere avec n'importe quel backend OTel. Les noms
d'attributs/operations sont les conventions semantiques GenAI canoniques tirees du
veritable `agent_framework/observability.py` (`invoke_agent` / `execute_tool`,
`gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.agent.name`,
`gen_ai.tool.name`). Sans dependance et deterministe (I4) : les ids de span/trace
sont un digest stable du run, les timestamps sont logiques (pas d'horloge murale),
de sorte que le meme run exporte des spans byte-identiques ; l'enregistrement est
en lecture seule (I1).

```mermaid
flowchart TD
  REC["OrchestrationRecording (team + run)"] --> RT["span racine : invoke_agent {team}"]
  RT --> A1["invoke_agent {participant}\ngen_ai.agent.name / .provider.name / .request.model"]
  RT --> A2["invoke_agent {participant}"]
  RT --> T1["execute_tool {tool}\ngen_ai.tool.name / .tool.call.id"]
  RT --> OTLP["to_otlp() -> ResourceSpans (OTLP/JSON)"]
  A1 --> OTLP
  A2 --> OTLP
  T1 --> OTLP
  OTLP --> BE["n'importe quel backend / collecteur OTel"]
```

```
python3 -m recette orchestrate otel /tmp/run.json --out spans.json
```

`recette/otel.py` : `orchestration_spans(team, run)` -> `to_otlp(spans)`. Un vrai
exporteur OTel (extra optionnel `[otel]`) reestampille les temps d'horloge murale a
l'emission ; la recette garantit seulement que la structure est reproductible.
