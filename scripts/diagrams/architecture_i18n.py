"""French->English label map for the ARCHITECTURE.md mermaid diagrams.

Single source of truth for diagram STRUCTURE stays in architecture.py (French
labels = default locale). This map turns each French diagram body into its
English equivalent line-by-line, so `gen_diagrams.py --write` can regenerate
BOTH locales (docs/ARCHITECTURE.md = fr, the i18n/en mirror = en) from the same
Python source. On a diagram evolution: edit architecture.py (fr), add any new
label line here, then re-run gen_diagrams.py --write. Stdlib only.
"""

from __future__ import annotations

# Exact French diagram-body line (rstrip) -> English line. Lines absent from
# this map (node ids, arrows, keywords, identifiers) are locale-neutral and
# pass through unchanged.
LABELS: dict[str, str] = {
    '  subgraph RECETTE["Plateforme de recette (ce repo)"]': '  subgraph RECETTE["Acceptance-testing platform (this repo)"]',
    '    CORPUS["Corpus ground-truth<br/>agents + repos"]': '    CORPUS["Ground-truth corpus<br/>agents + repos"]',
    '    PLATFORM["Plateforme d\'execution<br/>console + API + lab simule"]': '    PLATFORM["Execution platform<br/>console + API + simulated lab"]',
    '    HARNESS["Harnais<br/>discovery + identification"]': '    HARNESS["Harness<br/>discovery + identification"]',
    '    SCORE["Scorecards<br/>detection rate, accuracy par dimension"]': '    SCORE["Scorecards<br/>detection rate, accuracy per dimension"]',
    '  subgraph SUT["Outils sous test (externes, equipe discovery)"]': '  subgraph SUT["Tools under test (external, discovery team)"]',
    '    DISCO["Outil Discovery<br/>scanner de repos"]': '    DISCO["Discovery tool<br/>repo scanner"]',
    '    IDENT["Outil Identification<br/>juge 4 dimensions"]': '    IDENT["Identification tool<br/>judges 4 dimensions"]',
    '  PLATFORM -->|"agents vivants, traces"| HARNESS': '  PLATFORM -->|"live agents, traces"| HARNESS',
    '  HARNESS -->|"sujets a verite connue"| DISCO': '  HARNESS -->|"subjects with known truth"| DISCO',
    '  CORPUS -.->|"verite attendue"| SCORE': '  CORPUS -.->|"expected truth"| SCORE',
    '  subgraph CONSOLE["Console React (console/, :5173)"]': '  subgraph CONSOLE["React console (console/, :5173)"]',
    '    DASH["Tableau de bord<br/>statut live des agents"]': '    DASH["Dashboard<br/>live agent status"]',
    '    COCK["Cockpit (onglet de Agents)<br/>lancer/arreter + log reseau (proxy I5)"]': '    COCK["Cockpit (Agents tab)<br/>start/stop + network log (proxy I5)"]',
    '    RUNTAB["Recette<br/>runners discovery + identification"]': '    RUNTAB["Recette<br/>discovery + identification runners"]',
    '    CAMP["Campagnes<br/>templates, runs, replays"]': '    CAMP["Campaigns<br/>templates, runs, replays"]',
    '    AGENTS["Agents<br/>config, catalogue d\'actions, ai-backends"]': '    AGENTS["Agents<br/>config, action catalog, ai-backends"]',
    '    SRVTAB["Serveurs<br/>registre, start/stop, access log"]': '    SRVTAB["Servers<br/>registry, start/stop, access log"]',
    '  subgraph API["API FastAPI (recette/api/, extra [api])"]': '  subgraph API["FastAPI API (recette/api/, extra [api])"]',
    '    RM["RunManager<br/>runs en threads, frames bufferisees"]': '    RM["RunManager<br/>runs in threads, buffered frames"]',
    '    CFG["ConfigStore<br/>agents + ai-backends (JSON atomique)"]': '    CFG["ConfigStore<br/>agents + ai-backends (atomic JSON)"]',
    '    CSTORE["CampaignStore + RecordingStore<br/>campagnes + enregistrements"]': '    CSTORE["CampaignStore + RecordingStore<br/>campaigns + recordings"]',
    '    TPL["Campaign templates<br/>17 modeles predefinis"]': '    TPL["Campaign templates<br/>17 predefined templates"]',
    '  subgraph ENGINE["Moteur recette (recette/)"]': '  subgraph ENGINE["Recette engine (recette/)"]',
    '    LANEB["lane_b.run_agent<br/>boucle decide -> act"]': '    LANEB["lane_b.run_agent<br/>decide -> act loop"]',
    '    LLM["LlmBackend<br/>StubLlm / ReplayLlm<br/>8 providers live (cle env, R8)"]': '    LLM["LlmBackend<br/>StubLlm / ReplayLlm<br/>8 live providers (env key, R8)"]',
    '    FORGE["GitForge<br/>LabForge (defaut) / RealForge"]': '    FORGE["GitForge<br/>LabForge (default) / RealForge"]',
    '    REC["Recording<br/>artefact rejouable (I4)"]': '    REC["Recording<br/>replayable artifact (I4)"]',
    '    HARN["Harnais + Scorecards<br/>harness.py, discovery_harness.py"]': '    HARN["Harness + Scorecards<br/>harness.py, discovery_harness.py"]',
    '  subgraph LAB["Lab simule (recette/lab/, :8082)"]': '  subgraph LAB["Simulated lab (recette/lab/, :8082)"]',
    '    MOCK["Serveur mock unique<br/>16 domaines deterministes<br/>doubles realistes (champs metier, 422 si invalide)"]': '    MOCK["Single mock server<br/>16 deterministic domains<br/>realistic doubles (business fields, 422 if invalid)"]',
    "  pending --> running : worker thread demarre": "  pending --> running : worker thread starts",
    "  running --> completed : runner termine": "  running --> completed : runner finishes",
    "  running --> stopped : POST /runs/id/stop (cooperatif)": "  running --> stopped : POST /runs/id/stop (cooperative)",
    '    A1["Agent mock<br/>scenario stocke"]': '    A1["Mock agent<br/>stored scenario"]',
    '    A2["Agent IA reelle<br/>ai_backend + cle env"]': '    A2["Real AI agent<br/>ai_backend + env key"]',
    '  ROUTE{"binding server<br/>de l\'agent ?"}': '  ROUTE{"agent\'s server<br/>binding ?"}',
    '  REG["Registre de serveurs (config)<br/>mock_local / declared_url / real_saas"]': '  REG["Server registry (config)<br/>mock_local / declared_url / real_saas"]',
    '  subgraph SRV["Serveurs en face"]': '  subgraph SRV["Servers in front"]',
    '    LAB["Mock servers mock_local (config-driven, 12 serveurs :9101-9112)<br/>16 domaines: github gitlab okta finance support_desk slack cloud<br/>hris legal_dms product_cms data_platform crm knowledge_base mcp comms compliance<br/>doubles realistes (champs metier, 422 si invalide), deterministes<br/>POST /system/execute, access log JSONL + /health"]': '    LAB["mock_local mock servers (config-driven, 12 servers :9101-9112)<br/>16 domains: github gitlab okta finance support_desk slack cloud<br/>hris legal_dms product_cms data_platform crm knowledge_base mcp comms compliance<br/>realistic doubles (business fields, 422 if invalid), deterministic<br/>POST /system/execute, JSONL access log + /health"]',
    '    DECL["Serveur declare (declared_url)<br/>meme contrat wire que le lab"]': '    DECL["Declared server (declared_url)<br/>same wire contract as the lab"]',
    '    REAL["SaaS reels (real_saas)<br/>pas de proxy encore : run FAIL<br/>jamais de fallback (I5)"]': '    REAL["Real SaaS (real_saas)<br/>no proxy yet: run FAILS<br/>never a fallback (I5)"]',
    '    DR["Service discovery REEL<br/>du collegue (http_adapter)"]': '    DR["REAL discovery service<br/>from the colleague (http_adapter)"]',
    '  ROUTE -->|"aucun"| LF': '  ROUTE -->|"none"| LF',
    '  REG -->|"ProxyForge, vrai HTTP"| LAB': '  REG -->|"ProxyForge, real HTTP"| LAB',
    '  REG -->|"ProxyForge, vrai HTTP"| DECL': '  REG -->|"ProxyForge, real HTTP"| DECL',
    '  GW2["Gateway gouvernee<br/>(section 8)"] -->|"proxy I5, HTTP"| LAB': '  GW2["Governed gateway<br/>(section 8)"] -->|"proxy I5, HTTP"| LAB',
    '  HARN2["Harnais discovery"] -->|"memes routes REST"| DM': '  HARN2["Discovery harness"] -->|"same REST routes"| DM',
    '  subgraph T1["1. AVANT execution -- surface statique (source)"]': '  subgraph T1["1. BEFORE execution -- static surface (source)"]',
    '    SRC["Repo / artefact publie"]': '    SRC["Published repo / artifact"]',
    '    S2["code : import du SDK github/gitlab"]': '    S2["code: import of the github/gitlab SDK"]',
    '    S3["temporalio : @activity.defn (AST)"]': '    S3["temporalio: @activity.defn (AST)"]',
    '    S4["openapi.json : operationId"]': '    S4["openapi.json: operationId"]',
    '    S5["manifest MCP"]': '    S5["MCP manifest"]',
    '  subgraph T2["2. PENDANT execution -- surface runtime (serveur/reseau)"]': '  subgraph T2["2. DURING execution -- runtime surface (server/network)"]',
    '    W1["trafic API vers le systeme cible"]': '    W1["API traffic to the target system"]',
    '    W2["usage de credentials : QUEL principal,<br/>QUEL token appelle"]': '    W2["credential usage: WHICH principal,<br/>WHICH token calls"]',
    '    W3["frequence / pattern d\'appels"]': '    W3["frequency / call pattern"]',
    '  subgraph T3["3. APRES / EN CONTINU -- surface evenementielle (audit)"]': '  subgraph T3["3. AFTER / CONTINUOUS -- event surface (audit)"]',
    '    E1["action-log ordonne (AgentAction)"]': '    E1["ordered action-log (AgentAction)"]',
    '    E2["recordings rejouables (I4)"]': '    E2["replayable recordings (I4)"]',
    '    E3["event store gouverne :<br/>policy_decision, approval_state,<br/>side_effect_hash (I1)"]': '    E3["governed event store:<br/>policy_decision, approval_state,<br/>side_effect_hash (I1)"]',
    '  DISCO2["Moteur discovery"]': '  DISCO2["Discovery engine"]',
    '  T1 -->|"identite + capabilities DECLAREES"| DISCO2': '  T1 -->|"DECLARED identity + capabilities"| DISCO2',
    '  T2 -->|"identite + actions REELLES"| DISCO2': '  T2 -->|"REAL identity + actions"| DISCO2',
    '  T3 -->|"comportement complet, rejouable"| DISCO2': '  T3 -->|"complete, replayable behavior"| DISCO2',
    '  DECL["DECLARE<br/>(captation statique :<br/>manifest, scope, principal)"]': '  DECL["DECLARED<br/>(static capture:<br/>manifest, scope, principal)"]',
    '  OBS["OBSERVE<br/>(captation runtime + audit :<br/>actions, principal reel, approbations)"]': '  OBS["OBSERVED<br/>(runtime + audit capture:<br/>actions, real principal, approvals)"]',
    '  DECL -->|"principal declare vs principal observe"| D1["Dim 1 : Identite (I3)"]': '  DECL -->|"declared principal vs observed principal"| D1["Dim 1: Identity (I3)"]',
    '  DECL -->|"scope declare vs actions observees"| D2["Dim 2 : Capabilities"]': '  DECL -->|"declared scope vs observed actions"| D2["Dim 2: Capabilities"]',
    '  OBS -->|"actions escalate avec/sans approved"| D3["Dim 3 : Policy (I6)"]': '  OBS -->|"escalate actions with/without approved"| D3["Dim 3: Policy (I6)"]',
    '  OBS -->|"frequence, repetition, hors-role"| D4["Dim 4 : Comportement"]': '  OBS -->|"frequency, repetition, out-of-role"| D4["Dim 4: Behavior"]',
    '  D1 & D2 & D3 & D4 --> V["Verdict correct/incorrect<br/>vs ground-truth"]': '  D1 & D2 & D3 & D4 --> V["correct/incorrect verdict<br/>vs ground-truth"]',
    "  participant C as Console / campagne": "  participant C as Console / campaign",
    "  loop max_steps (10 par defaut)": "  loop max_steps (10 by default)",
    "    L-->>B: LlmDecision (tool_call ou final)": "    L-->>B: LlmDecision (tool_call or final)",
    "      F-->>B: AgentAction (seq, ts logique, mode)": "      F-->>B: AgentAction (seq, logical ts, mode)",
    "      Note over B: sortie de boucle": "      Note over B: exit loop",
    '    +timestamp : str  "LogicalClock, pas now()"': '    +timestamp : str  "LogicalClock, not now()"',
    '    +principal : str  "identite REELLEMENT utilisee"': '    +principal : str  "identity ACTUALLY used"',
    '    +action_type : str  "action du catalogue"': '    +action_type : str  "catalog action"',
    '    +approved : bool  "approbation prealable (I6)"': '    +approved : bool  "prior approval (I6)"',
    "  RecordedStep --> AgentAction : serialise": "  RecordedStep --> AgentAction : serializes",
    "  participant RUN as Run live (IA reelle ou mock)": "  participant RUN as Live run (real AI or mock)",
    "  participant RPL as Run replay": "  participant RPL as Replay run",
    "  Note over RS: JSON versionne (schema_version 1.0)": "  Note over RS: versioned JSON (schema_version 1.0)",
    "  RPL->>RPL: ReplayLlm re-emet les decisions dans l'ordre": "  RPL->>RPL: ReplayLlm re-emits the decisions in order",
    "  title Les deux axes d'un agent de recette": "  title The two axes of a recette agent",
    "  x-axis Cible simulee lab --> Cible reelle": "  x-axis Simulated lab target --> Real target",
    "  y-axis IA mock scenario --> IA reelle LLM": "  y-axis Mock scenario AI --> Real LLM AI",
    "  quadrant-1 Validation finale outillee": "  quadrant-1 Tooled final validation",
    "  quadrant-2 Exploration comportement IA": "  quadrant-2 AI behavior exploration",
    "  quadrant-3 Corpus deterministe defaut": "  quadrant-3 Default deterministic corpus",
    "  quadrant-4 Test integration cible": "  quadrant-4 Target integration test",
    "  Templates de campagne: [0.2, 0.2]": "  Campaign templates: [0.2, 0.2]",
    "  Corpus identification: [0.12, 0.12]": "  Identification corpus: [0.12, 0.12]",
    "  Cockpit IA live: [0.25, 0.8]": "  Live AI cockpit: [0.25, 0.8]",
    "  Run final org de test: [0.85, 0.85]": "  Final test-org run: [0.85, 0.85]",
    "  participant U as Equipe discovery": "  participant U as Discovery team",
    "  API-->>U: agent mock + campagne crees (idempotent)": "  API-->>U: mock agent + campaign created (idempotent)",
    "  API->>CR: run en thread (frames live via WS)": "  API->>CR: run in thread (live frames via WS)",
    "  loop chaque etape (agent)": "  loop each step (agent)",
    "    CR->>CR: resolve agent (scenario mock OU ai_backend reel)": "    CR->>CR: resolve agent (mock scenario OR real ai_backend)",
    '    CR->>ST: save(recording "campagne.etape.agent")': '    CR->>ST: save(recording "campaign.step.agent")',
    "  API-->>U: replay_result IDENTIQUE / DIVERGENT": "  API-->>U: replay_result IDENTICAL / DIVERGENT",
    '    PROXY["ExternalSystemProxy (proxy/)<br/>seul contact externe<br/>produit side_effect_hash"]': '    PROXY["ExternalSystemProxy (proxy/)<br/>sole external contact<br/>produces side_effect_hash"]',
    '    LAB2["Lab mock :8082<br/>16 domaines, handlers purs (doubles realistes)"]': '    LAB2["Mock lab :8082<br/>16 domains, pure handlers (realistic doubles)"]',
    '    ES["EventStore SQLite<br/>INSERT-only, triggers anti-UPDATE/DELETE<br/>hash chain, WAL"]': '    ES["EventStore SQLite<br/>INSERT-only, anti-UPDATE/DELETE triggers<br/>hash chain, WAL"]',
    '  SCHED["Scheduler (G8)<br/>opt-in INSPECT_IA_AGENTS_SCHEDULER<br/>hors decision (I4), fail-safe"]': '  SCHED["Scheduler (G8)<br/>opt-in INSPECT_IA_AGENTS_SCHEDULER<br/>off the decision path (I4), fail-safe"]',
    '  GW -->|"chaque transition"| ES': '  GW -->|"each transition"| ES',
    '  SCHED -.->|"flush realtime buffer (vue derivee I1)"| PROXY': '  SCHED -.->|"flush realtime buffer (derived view I1)"| PROXY',
}


def translate(diagram_body: str) -> str:
    """Return the English version of a French mermaid diagram body."""
    out = []
    for line in diagram_body.splitlines():
        key = line.rstrip()
        if key in LABELS:
            # preserve trailing newline semantics by using the mapped line
            out.append(LABELS[key])
        else:
            out.append(line)
    return "\n".join(out)
