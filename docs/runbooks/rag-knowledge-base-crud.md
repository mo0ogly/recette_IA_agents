# RAG knowledge-base CRUD + poison scenarios + reset

Operator lifecycle to prepare and run the RAG poisoning recette: view the
knowledge base, insert/delete documents, apply a named poison scenario, and reset
to the clean baseline. This is a banc-de-test tool **off the agent path** -- it
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
`invalid-command-ops` (unknown command). Add one by dropping a new file; the
KB-guard in `tests/test_rag_poisoning.py` keeps poisoned docs aligned with
campaigns.

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
- **I4 reset determinism**: `reset()` reloads the baseline byte-for-byte
  (`test_reset_is_deterministic`).

## Tests

- `tests/test_rag_store.py` -- CRUD, reset determinism, scenario injection, the lab
  handler reflecting the store, path-traversal rejection.
- `tests/test_api_rag_kb.py` -- the six routes + the I2 anti-backdoor guarantee.
- `console/src/pages/rag/KnowledgeBaseManager.test.tsx` -- R16 render-and-assert
  against a real captured payload.
