# RAG for AgentRail recette -- Design

Date : 2026-06-13
Status : VALIDATED (brainstorm)
Scope : new RAG capability across the recette platform (Python) + console (React/TS)

## Goal

Add Retrieval-Augmented-Generation as a first-class capability of the AgentRail
recette platform, serving four roles around one canonical foundation: a RAG
test agent (ground-truth subject), retrieval infrastructure for real LLM agents,
recette of an external RAG tool, and a console menu.

## Context (verified)

No RAG exists in the codebase today (zero retrieval/embedding/vector/knowledge-base).
The platform validates external discovery/identification tools via a ground-truth
corpus and runs real agents driven by 11 LLM providers. Recette code is Python
(`recette/`), console is React/TS. Canonical event model `AgentActionEvent`,
determinism I4, secrets via env R8, lab-simulated by default.

## Architecture

### 1. Canonical RAG actions (foundation)

New `action_type` values mapped onto `AgentActionEvent`:

| action_type | target_system | default risk | default verdict |
|-------------|---------------|--------------|-----------------|
| `rag_retrieve` | `knowledge_base` | low | allow |
| `rag_embed` | `knowledge_base` | low | allow |
| `rag_index` | `knowledge_base` | medium | escalate-for-privileged |

Defined in the action catalog (same place as the existing github/gitlab actions).
Determinism I4: `event_id` derived from the logical sequence, no clock; for the
real backend the retrieved doc ids + scores are captured as event inputs so a
replay re-reads them rather than re-querying.

### 2. RagBackend protocol (recette/rag.py) -- both impls from the start

Symmetric to the existing `LlmBackend` (stub + real providers):

```
class RagBackend(Protocol):
    def retrieve(self, query: str, *, k: int) -> list[RetrievedDoc]: ...
    def index(self, docs: list[Document]) -> IndexReport: ...

class DeterministicRagBackend:   # lab default, no hard dependency
    # fixed in-memory corpus, deterministic lexical scoring (token overlap / BM25-like),
    # stable tie-break by doc id. Reproducible, I4-safe.

class RealRagBackend:            # optional extra [rag]
    # embeddings via the existing LLM providers (or a dedicated embeddings endpoint)
    # + a vector store (FAISS / pgvector). Non-determinism captured in the event.
    # Secrets via env (R8). HTTP client injectable for offline tests (like LlmBackend).
```

`build_rag(kind, ...)` factory mirrors `build_llm`.

### 3. Role -- RAG test agent (ground-truth subject)

Corpus agents (positives + one negative per violation_type) that declare RAG
capabilities and perform RAG actions:
- positive: declares `rag_retrieve`, retrieves relevant docs, stays in scope.
- `capability_overreach`: declares retrieve-only, performs `rag_index`.
- `behavior_anomaly`: retrieves off-topic / irrelevant docs.
Discovery must detect them; identification judges the 4 dimensions. Each carries
manifest + scenario + ground-truth, validated against the existing schemas
(extended with the new action types).

### 4. Role -- recette of an external RAG tool

`RagAdapter` protocol (like `DiscoveryAdapter` / `IdentificationAdapter`) +
`ReferenceRagAdapter` as the correct-by-reference oracle. Ground-truth = invariant
properties only (the expected docs are retrieved, relative relevance ordering,
determinism), never the opaque scores. CLI: `python -m recette rag --adapter reference|http`.
Scorecard: retrieval precision/recall vs ground-truth, ordering correctness.

### 5. Role -- retrieval infra for real agents

Real LLM agents call `rag_retrieve` through a mediated proxy (I5) during their
loop; the retrieved context is injected into the next LLM turn. The retrieval
result is an audited side effect (`side_effect_hash`).

### 6. Role -- console menu

New `/rag` page: knowledge base view, RAG agents list, RAG recette scorecard,
and a LogConsole for retrieval calls. Reuses the existing console patterns
(LogConsole, fixtures + render-and-assert per R16, shared lib helpers).

## Data flow

```
agent action -> normalize to AgentActionEvent (action_type=rag_*) -> policy verdict
   -> RagBackend.retrieve/index (deterministic or real)
   -> retrieved docs captured as event inputs (I4) + side_effect_hash (I1/I5)
   -> identification judges 4 dimensions vs ground-truth -> scorecard
```

## Error handling / failure modes

- RagBackend unavailable -> deny/freeze the action (fail-safe), audited failure event.
- Real backend: missing API key -> RuntimeError naming the env var (like LlmBackend), never a silent fallback.
- Determinism: real retrieval results captured; replay re-reads, never re-queries.

## Testing

- `DeterministicRagBackend`: unit tests on scoring + stable ordering (I4 replay test).
- `RealRagBackend`: offline tests via injected HTTP client (no key/network), like test_llm.py.
- Corpus agents: schema-validated; `test_each_negative_breaks_exactly_one_dimension` extended.
- `RagAdapter`: reference oracle test + scorecard aggregation test.
- Console: fixtures + render-and-assert (R16) for the /rag page.

## Phasing (YAGNI -- foundation first)

- **P1** : canonical RAG actions + `RagBackend` (deterministic + real) + tests.
- **P2** : RAG test-agent corpus + recette `RagAdapter` + scorecard + CLI.
- **P3** : retrieval infra wired into the real-agent loop (proxy-mediated, I5).
- **P4** : console `/rag` menu.

Each phase ships independently green (build + tests). `audit-pdca --fix` runs after each.

## Invariants touched

I1 (immutable retrieval side-effect events), I4 (deterministic replay -- captured
retrieval inputs), I5 (retrieval via mediated proxy), plus the canonical event
model extension (versioned, no destructive migration).
