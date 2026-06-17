# RAG knowledge-base CRUD + poison scenarios + reset

Operator lifecycle to prepare and run the RAG poisoning recette: view the
knowledge base, insert/delete documents, apply a named poison scenario, and reset
to the clean baseline. This is a test-bench tool **off the agent path** -- it
never lets an agent mutate the index without the gateway (I2).

## Why

The RAG poisoning recette proves that a polluted knowledge base cannot make an
agent produce a forbidden side effect: even if a retrieved document instructs the
agent to exfiltrate / run an invalid command / ingest forged data, the gateway
denies or escalates the induced action. To run that recette repeatably you need
to *pollute* the knowledge base in a controlled way and *reset* it afterwards.
This feature provides that lifecycle.

## Model (deterministic, I4)

- The baseline is the committed file `corpus/rag/knowledge_base.json` (source of
  truth).
- A single in-memory document list (`recette/rag_store.py`, `live_documents()`) is
  seeded from the baseline and shared with the lab handler
  (`recette/lab/domains/knowledge_base.py`), so a live agent `query_knowledge_base`
  reflects the current state (baseline + applied scenario).
- `reset()` reloads the baseline exactly -- same bytes every time, no clock, no
  random. The recette loop is therefore replayable.

## The recette loop

```
reset -> apply <scenario> -> run agent / campaign -> gateway denies/escalates -> reset
```

The gateway verdict is what the recette asserts: the induced action is `deny`
(exfil / unknown command) or `escalate` (index mutation), `executed=False`. See
`campaigns/rag/` and `scripts/run_rag_poisoning_live_groq.py`.

## Diagrams (for the recette team)

### Where the operator CRUD sits vs the agent path (I2 boundary)

The operator mutates the knowledge base directly (test-bench). The agent never
does: it can only read via a mediated `query_knowledge_base`, and any side effect
the poisoned content induces is decided by the gateway -- not by the RAG content.

```mermaid
flowchart LR
  subgraph Operator["Operator test-bench (off the agent path)"]
    CLI["CLI: recette rag-kb"]
    UI["Console /rag KnowledgeBaseManager"]
    ROUTES["/rag/* operator routes"]
    STORE["KnowledgeBaseStore (rag_store.py)"]
  end
  subgraph Shared["Shared in-memory KB"]
    LIVE["live_documents() = baseline + applied scenario"]
  end
  subgraph AgentPath["Agent path (mediated, I2)"]
    AGENT["RAG agent"]
    GW["Gateway /actions/execute"]
    POLICY["Policy engine decide()"]
    LAB["lab knowledge_base handler"]
  end
  BASELINE[("corpus/rag/knowledge_base.json")]
  SCEN[("corpus/rag/scenarios/*.json")]

  CLI --> ROUTES
  UI --> ROUTES
  ROUTES --> STORE
  STORE -->|reset| BASELINE
  STORE -->|apply scenario| SCEN
  STORE --> LIVE
  AGENT -->|query_knowledge_base| GW
  GW --> POLICY
  POLICY -->|allow read| LAB
  LAB -->|reads| LIVE
  AGENT -.->|induced side effect| GW
  GW -.->|deny / escalate, executed=False| AGENT
```

### The poisoning recette loop (sequence)

```mermaid
sequenceDiagram
  participant Op as Operator
  participant Store as KnowledgeBaseStore
  participant KB as Shared KB
  participant Agent as RAG agent
  participant GW as Gateway + policy
  Op->>Store: reset()
  Store->>KB: clean baseline
  Op->>Store: apply_scenario("exfil-finance")
  Store->>KB: inject poisoned doc scn-exfil-finance
  Agent->>GW: query_knowledge_base
  GW->>KB: read (allow)
  KB-->>Agent: returns the poisoned document
  Agent->>GW: send_data_to_external_domain (demanded by the poison)
  GW-->>Agent: DENY -- executed=False (I2)
  Op->>Store: reset()
  Store->>KB: baseline restored (poison gone, I4)
```

### The two CI guards that keep a poison honest (T4 + T5)

A poison artifact cannot enter the corpus without proof it is blocked, and an
inserted document cannot carry a stray identifier.

```mermaid
flowchart TD
  NEW["New / edited poison artifact"] --> Q1{"poisoned doc in a scenario file?"}
  Q1 -->|yes| G4["T4 scenario guard: gateway decision for rag_agent on the injected action equals injected_expect, and injected_expect is deny or escalate"]
  G4 -->|mismatch or allow| RED1["suite RED: no proof of blocking"]
  G4 -->|match| Q2
  Q1 -->|no| Q2{"inserted via store.add?"}
  Q2 -->|yes| G5["T5 id guard: id matches the corpus slug pattern"]
  G5 -->|invalid id| RED2["KnowledgeBaseError"]
  G5 -->|valid| OK["accepted into the corpus"]
  Q2 -->|no| OK
```

## CLI

```
python -m recette rag-kb list
python -m recette rag-kb scenarios
python -m recette rag-kb apply --scenario exfil-finance
python -m recette rag-kb add --doc path/to/doc.json
python -m recette rag-kb del --id <doc-id>
python -m recette rag-kb reset
```

A document JSON has `id, title, content, poisoned, tags`; a poisoned document also
carries `injected_action, injected_target_system, injected_expect, threat`.

## HTTP API (operator routes, off the agent path)

| Method | Route | Purpose |
|--------|-------|---------|
| GET | `/rag/documents` | list the current knowledge base |
| POST | `/rag/documents` | insert a document (400 on invalid) |
| DELETE | `/rag/documents/{id}` | remove a document (404 if unknown) |
| POST | `/rag/reset` | restore the clean baseline |
| GET | `/rag/scenarios` | list named poison scenarios |
| POST | `/rag/scenario/{name}/apply` | inject a named scenario's documents |

Responses are plain JSON dicts (no `{success, data}` envelope -- matches the rest
of the API). The console page `/rag` renders the `KnowledgeBaseManager` below the
retrieval scorecard.

## Scenarios

`corpus/rag/scenarios/*.json`, validated by `scenario.schema.json`. Each is a named
set of documents to inject. Shipped: `exfil-finance` (exfiltration),
`invalid-command-ops` (unknown command). Add one by dropping a new file. Two guards
keep a scenario honest:

- **scenario guard (T4)** -- for every poisoned doc in every scenario file,
  `tests/test_rag_poisoning.py::test_scenario_guard_every_poisoned_doc_is_blocked_by_the_gateway`
  decides the injected action for a `rag_agent` and asserts the verdict equals the
  doc's `injected_expect` AND is a block (`deny`/`escalate`). A scenario whose poison
  is actually allowed, or whose stated `injected_expect` drifts from the engine,
  turns the suite RED -- no poison ships without decide-based proof it is blocked.
- **KB-seed guard** -- `test_kb_guard_every_poisoned_doc_has_a_campaign` keeps the
  poisoned docs of `knowledge_base.json` aligned with a `campaigns/rag/` campaign.

## Security / invariants

- **I2 anti-backdoor**: the operator CRUD is on `/rag/*` routes, never on the agent
  `/actions/execute` path. An agent attempting `ingest_document` still ESCALATES
  through the gateway (`tests/test_api_rag_kb.py::test_anti_backdoor_...`). The CRUD
  does not open a mutation bypass.
- **Path traversal**: a scenario `name` is validated against `^[a-z0-9][a-z0-9-]{1,63}$`
  and the resolved path must stay inside the scenarios directory, so
  `apply_scenario("../knowledge_base")` or an absolute path is rejected
  (`test_apply_scenario_rejects_path_traversal`). Without this guard a crafted name
  could load an arbitrary `.json` from disk.
- **Id slug (T5, defence in depth)**: an inserted document `id` must match the same
  slug `^[a-z0-9][a-z0-9-]{1,63}$` as the schema. The id touches no file path, but
  enforcing the corpus shape at the store rejects stray identifiers early
  (`test_add_rejects_invalid_id_slug`).
- **I4 reset determinism**: `reset()` reloads the baseline byte-for-byte
  (`test_reset_is_deterministic`).

## Tests

- `tests/test_rag_store.py` -- CRUD, reset determinism, scenario injection, the lab
  handler reflecting the store, path-traversal rejection, id-slug rejection (T5).
- `tests/test_api_rag_kb.py` -- the six routes + the I2 anti-backdoor guarantee.
- `tests/test_rag_poisoning.py` -- decide-based verdicts of every `campaigns/rag/`
  action, the KB-seed campaign guard, and the scenario poison guard (T4).
- `console/src/pages/rag/KnowledgeBaseManager.test.tsx` -- R16 render-and-assert
  against a real captured payload.
- System recette LEG C (`scripts/run_system_recette.py`) exercises the full
  reset -> apply -> campaign -> anti-backdoor loop end to end.
