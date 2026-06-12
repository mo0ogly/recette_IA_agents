"""Mermaid diagram sources for docs/ARCHITECTURE.md.

Single source of truth for every mermaid block in the foundational
architecture document. Edit a diagram HERE, then re-inject it with:

    python3 scripts/gen_diagrams.py --write     # update the markdown
    python3 scripts/gen_diagrams.py --check     # CI / librarian drift gate
    python3 scripts/gen_diagrams.py --render    # validate via mmdc if installed

Each entry maps a marker name (``<!-- mermaid:NAME -->`` in the markdown)
to the diagram body. Stdlib only.
"""

from __future__ import annotations


def context_recette() -> str:
    """Diagram 'context-recette'."""
    return """\
flowchart LR
  subgraph RECETTE["Plateforme de recette (ce repo)"]
    CORPUS["Corpus ground-truth<br/>agents + repos"]
    PLATFORM["Plateforme d'execution<br/>console + API + lab simule"]
    HARNESS["Harnais<br/>discovery + identification"]
    SCORE["Scorecards<br/>detection rate, accuracy par dimension"]
  end
  subgraph SUT["Outils sous test (externes, equipe discovery)"]
    DISCO["Outil Discovery<br/>scanner de repos"]
    IDENT["Outil Identification<br/>juge 4 dimensions"]
  end
  CORPUS --> HARNESS
  PLATFORM -->|"agents vivants, traces"| HARNESS
  HARNESS -->|"sujets a verite connue"| DISCO
  HARNESS -->|"action-logs + manifests"| IDENT
  DISCO -->|"detections"| HARNESS
  IDENT -->|"verdicts"| HARNESS
  HARNESS --> SCORE
  CORPUS -.->|"verite attendue"| SCORE
"""


def components() -> str:
    """Diagram 'components'."""
    return """\
flowchart TB
  subgraph CONSOLE["Console React (console/, :5173)"]
    DASH["Tableau de bord<br/>statut live des agents"]
    COCK["Cockpit<br/>lancer / arreter un agent"]
    RUNTAB["Recette<br/>runners discovery + identification"]
    CAMP["Campagnes<br/>templates, runs, replays"]
    AGENTS["Agents<br/>config, catalogue d'actions, ai-backends"]
    SRVTAB["Serveurs<br/>registre, start/stop, access log"]
  end

  subgraph API["API FastAPI (recette/api/, extra [api])"]
    RM["RunManager<br/>runs en threads, frames bufferisees"]
    CFG["ConfigStore<br/>agents + ai-backends (JSON atomique)"]
    CSTORE["CampaignStore + RecordingStore<br/>campagnes + enregistrements"]
    TPL["Campaign templates<br/>17 modeles predefinis"]
  end

  subgraph ENGINE["Moteur recette (recette/)"]
    LANEB["lane_b.run_agent<br/>boucle decide -> act"]
    LLM["LlmBackend<br/>StubLlm / ReplayLlm<br/>8 providers live (cle env, R8)"]
    FORGE["GitForge<br/>LabForge (defaut) / RealForge"]
    REC["Recording<br/>artefact rejouable (I4)"]
    HARN["Harnais + Scorecards<br/>harness.py, discovery_harness.py"]
  end

  subgraph LAB["Lab simule (recette/lab/, :8082)"]
    MOCK["Serveur mock unique<br/>12 domaines deterministes"]
  end

  CONSOLE -->|"HTTP + WebSocket"| API
  RM --> LANEB
  LANEB --> LLM
  LANEB --> FORGE
  LANEB --> REC
  RM --> HARN
  HARN -->|"adapters"| LAB
  CSTORE --> REC
"""


def run_lifecycle() -> str:
    """Diagram 'run-lifecycle'."""
    return """\
stateDiagram-v2
  [*] --> pending : POST /runs
  pending --> running : worker thread demarre
  running --> completed : runner termine
  running --> failed : exception (frame error)
  running --> stopped : POST /runs/id/stop (cooperatif)
  completed --> [*]
  failed --> [*]
  stopped --> [*]
"""


def lab_topology() -> str:
    """Diagram 'lab-topology'."""
    return """\
flowchart LR
  subgraph AGENTS["Agents (Lane B)"]
    A1["Agent mock<br/>scenario stocke"]
    A2["Agent IA reelle<br/>ai_backend + cle env"]
  end
  ROUTE{"binding server<br/>de l'agent ?"}
  REG["Registre de serveurs (config)<br/>mock_local / declared_url / real_saas"]
  subgraph SRV["Serveurs en face"]
    direction TB
    LF["LabForge<br/>in-memory, in-process"]
    LAB["Lab mock :8082 (mock_local)<br/>POST /system/execute<br/>access log JSONL + /health"]
    DECL["Serveur declare (declared_url)<br/>meme contrat wire que le lab"]
    REAL["SaaS reels (real_saas)<br/>pas de proxy encore : run FAIL<br/>jamais de fallback (I5)"]
  end
  subgraph DPLANE["Discovery / Enrichment Plane"]
    DM["Mock discovery :8081<br/>sources / scan-runs / risks"]
    DR["Service discovery REEL<br/>du collegue (http_adapter)"]
  end
  A1 --> ROUTE
  A2 --> ROUTE
  ROUTE -->|"aucun"| LF
  ROUTE -->|"server=id"| REG
  REG -->|"ProxyForge, vrai HTTP"| LAB
  REG -->|"ProxyForge, vrai HTTP"| DECL
  REG -.->|"ValueError"| REAL
  GW2["Gateway gouvernee<br/>(section 8)"] -->|"proxy I5, HTTP"| LAB
  HARN2["Harnais discovery"] -->|"memes routes REST"| DM
  HARN2 -->|"AGENTRAIL_DISCOVERY_URL"| DR
"""


def capture_points() -> str:
    """Diagram 'capture-points'."""
    return """\
flowchart TB
  subgraph T1["1. AVANT execution -- surface statique (source)"]
    SRC["Repo / artefact publie"]
    S1["manifest .agentrail/manifest.json"]
    S2["code : import du SDK github/gitlab"]
    S3["temporalio : @activity.defn (AST)"]
    S4["openapi.json : operationId"]
    S5["manifest MCP"]
    SRC --- S1 & S2 & S3 & S4 & S5
  end
  subgraph T2["2. PENDANT execution -- surface runtime (serveur/reseau)"]
    W1["trafic API vers le systeme cible"]
    W2["usage de credentials : QUEL principal,<br/>QUEL token appelle"]
    W3["frequence / pattern d'appels"]
  end
  subgraph T3["3. APRES / EN CONTINU -- surface evenementielle (audit)"]
    E1["action-log ordonne (AgentAction)"]
    E2["recordings rejouables (I4)"]
    E3["event store gouverne :<br/>policy_decision, approval_state,<br/>side_effect_hash (I1)"]
  end
  DISCO2["Moteur discovery"]
  T1 -->|"identite + capabilities DECLAREES"| DISCO2
  T2 -->|"identite + actions REELLES"| DISCO2
  T3 -->|"comportement complet, rejouable"| DISCO2
"""


def capture_to_dimensions() -> str:
    """Diagram 'capture-to-dimensions'."""
    return """\
flowchart LR
  DECL["DECLARE<br/>(captation statique :<br/>manifest, scope, principal)"]
  OBS["OBSERVE<br/>(captation runtime + audit :<br/>actions, principal reel, approbations)"]
  DECL -->|"principal declare vs principal observe"| D1["Dim 1 : Identite (I3)"]
  DECL -->|"scope declare vs actions observees"| D2["Dim 2 : Capabilities"]
  OBS -->|"actions escalate avec/sans approved"| D3["Dim 3 : Policy (I6)"]
  OBS -->|"frequence, repetition, hors-role"| D4["Dim 4 : Comportement"]
  D1 & D2 & D3 & D4 --> V["Verdict correct/incorrect<br/>vs ground-truth"]
"""


def lane_b_loop() -> str:
    """Diagram 'lane-b-loop'."""
    return """\
sequenceDiagram
  participant C as Console / campagne
  participant R as RunManager
  participant B as lane_b.run_agent
  participant L as LlmBackend
  participant F as Forge (LabForge)
  participant REC as Recording
  C->>R: POST /runs kind=lane_b
  R->>B: run_agent(goal, capability_scope, llm)
  loop max_steps (10 par defaut)
    B->>L: decide(system, history, tools)
    L-->>B: LlmDecision (tool_call ou final)
    alt tool_call
      B->>F: execute(action_type, resource)
      F-->>B: AgentAction (seq, ts logique, mode)
      B->>REC: append(decision, action)
      B-->>R: frame step
    else final
      B->>REC: append(decision, null)
      Note over B: sortie de boucle
    end
  end
  B-->>R: LaneBResult(actions, recording)
  R-->>C: frames result + end
"""


def agent_action_model() -> str:
    """Diagram 'agent-action-model'."""
    return """\
classDiagram
  class AgentAction {
    +event_id : str  "evt-NNNN, sequence"
    +seq : int
    +timestamp : str  "LogicalClock, pas now()"
    +agent_id : str
    +principal : str  "identite REELLEMENT utilisee"
    +target_system : str
    +action_type : str  "action du catalogue"
    +mode : str  "read | write"
    +resource : str
    +approved : bool  "approbation prealable (I6)"
    +params : dict
  }
  class Recording {
    +agent_id, principal, target_system, goal
    +provider, model
    +steps : RecordedStep[]
    +actions() dict[]
  }
  class RecordedStep {
    +decision : LlmDecision
    +action : dict or null
  }
  Recording "1" o-- "n" RecordedStep
  RecordedStep --> AgentAction : serialise
"""


def record_replay() -> str:
    """Diagram 'record-replay'."""
    return """\
sequenceDiagram
  participant RUN as Run live (IA reelle ou mock)
  participant RS as RecordingStore (data/recordings/)
  participant RPL as Run replay
  RUN->>RS: save(recording)  "decisions + actions"
  Note over RS: JSON versionne (schema_version 1.0)
  RPL->>RS: load(recording_id)
  RPL->>RPL: ReplayLlm re-emet les decisions dans l'ordre
  RPL->>RPL: re-execution via LabForge
  RPL-->>RUN: replay_result.matches_original = true/false
"""


def agent_axes() -> str:
    """Diagram 'agent-axes'."""
    return """\
quadrantChart
  title Les deux axes d'un agent de recette
  x-axis Cible simulee lab --> Cible reelle
  y-axis IA mock scenario --> IA reelle LLM
  quadrant-1 Validation finale outillee
  quadrant-2 Exploration comportement IA
  quadrant-3 Corpus deterministe defaut
  quadrant-4 Test integration cible
  Templates de campagne: [0.2, 0.2]
  Corpus identification: [0.12, 0.12]
  Cockpit IA live: [0.25, 0.8]
  Run final org de test: [0.85, 0.85]
"""


def campaign_flow() -> str:
    """Diagram 'campaign-flow'."""
    return """\
sequenceDiagram
  participant U as Equipe discovery
  participant API as API /campaigns
  participant CR as Campaign runner
  participant ST as RecordingStore
  U->>API: POST /campaign-templates/finance-wire-fraud/instantiate
  API-->>U: agent mock + campagne crees (idempotent)
  U->>API: POST /campaigns/finance-wire-fraud/run
  API->>CR: run en thread (frames live via WS)
  loop chaque etape (agent)
    CR->>CR: resolve agent (scenario mock OU ai_backend reel)
    CR->>CR: lane_b.run_agent(...)
    CR->>ST: save(recording "campagne.etape.agent")
    CR-->>U: frames agent_start / step / agent_done
  end
  CR-->>U: campaign_done
  U->>API: POST /recordings/id/replay
  API-->>U: replay_result IDENTIQUE / DIVERGENT
"""


def governed_path() -> str:
    """Diagram 'governed-path'."""
    return """\
flowchart TB
  AGENT["Agent / console / curl"] --> GW
  subgraph CONTROL["Control Plane"]
    GW["Gateway (gateway.py)<br/>resolve agent -> normalize -><br/>PlatformActionEvent"]
    POL["Policy Engine (policy/)<br/>decide(event, policy) PURE<br/>deny-by-default, versions"]
    APP["Approvals (approvals/)<br/>state machine<br/>pending->approved/denied/timeout"]
    GW --> POL
    POL -->|"escalate"| APP
  end
  subgraph DATA["Data Plane"]
    PROXY["ExternalSystemProxy (proxy/)<br/>seul contact externe<br/>produit side_effect_hash"]
    LAB2["Lab mock :8082<br/>12 domaines, handlers purs"]
    PROXY --> LAB2
  end
  subgraph AUDIT["Audit Plane"]
    ES["EventStore SQLite<br/>INSERT-only, triggers anti-UPDATE/DELETE<br/>hash chain, WAL"]
  end
  POL -->|"allow / approved"| PROXY
  POL -->|"deny"| ES
  GW -->|"chaque transition"| ES
  PROXY -->|"action_executed + hash"| ES
"""


DIAGRAMS: dict[str, str] = {
    "context-recette": context_recette(),
    "components": components(),
    "run-lifecycle": run_lifecycle(),
    "lab-topology": lab_topology(),
    "capture-points": capture_points(),
    "capture-to-dimensions": capture_to_dimensions(),
    "lane-b-loop": lane_b_loop(),
    "agent-action-model": agent_action_model(),
    "record-replay": record_replay(),
    "agent-axes": agent_axes(),
    "campaign-flow": campaign_flow(),
    "governed-path": governed_path(),
}
