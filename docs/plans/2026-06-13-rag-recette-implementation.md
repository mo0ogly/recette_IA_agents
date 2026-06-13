# RAG Recette Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add RAG as a first-class recette capability: canonical rag_* actions + a RagBackend protocol with a deterministic (lab) and a real impl, then test agents, external-tool recette, runtime infra, and a console menu.

**Architecture:** A new `knowledge_base` catalog domain defines the rag_* actions and their role-based verdicts. `recette/rag.py` mirrors `recette/llm.py` (Protocol + stub/deterministic + real impls + injectable HTTP client + `build_rag` factory). Determinism I4: deterministic lexical scoring with stable tie-break; real retrieval results are captured as event inputs. Real vector store is an optional extra `[rag]`.

**Tech Stack:** Python (package `recette/`), unittest stdlib, ruff + mypy + bandit, jsonschema only hard dep. Mirrors existing `recette/llm.py` + `recette/platform/catalog/`.

---

## Phase 1 -- Foundation (canonical actions + RagBackend)

> COORDINATION (2026-06-13): Task 1 below is SUPERSEDED. The `knowledge_base`
> catalog domain is already built and actively owned by the parallel
> RAG-poisoning track (canonical actions `query_knowledge_base`,
> `ingest_document`, `update_retrieval_config`, `export_knowledge_base`,
> `delete_document`, `purge_index`; privileged role `rag_agent`; regenerated
> role-matrix campaigns + a `rag_agent` campaign). Do NOT build a competing
> domain (R28 flag-not-sweep). The committed `recette/rag.py` (Task 2-6, on
> main at 3c24bb6) is the execution engine behind that domain:
> `query_knowledge_base -> RagBackend.retrieve`, `ingest_document ->
> RagBackend.index`. Wiring the engine to the domain happens once their domain
> lands on main (Phase 3).

### Task 1: knowledge_base catalog domain (DONE by parallel track -- do not duplicate)

**Files:**
- Create: `recette/platform/catalog/domains/knowledge_base.py`
- Modify: `recette/platform/catalog/domains/__init__.py` (add `"knowledge_base"` to `DOMAIN_MODULES`)
- Test: `tests/test_catalog.py` (or the existing catalog test file -- add cases)

**Step 1: Write the failing test**

```python
def test_knowledge_base_actions_present(self):
    cat = build_catalog()  # existing helper that loads DOMAIN_MODULES
    assert cat.get("knowledge_base", "rag_retrieve") is not None
    assert cat.get("knowledge_base", "rag_index") is not None
    assert cat.get("knowledge_base", "rag_embed") is not None

def test_rag_retrieve_is_low_allow_for_any_role(self):
    spec = build_catalog().get("knowledge_base", "rag_retrieve")
    assert spec.risk_level == RiskLevel.LOW
    assert spec.verdict_for_role("anyone") == PolicyVerdict.ALLOW

def test_rag_index_escalates_for_privileged_denies_others(self):
    spec = build_catalog().get("knowledge_base", "rag_index")
    assert spec.verdict_for_role("kb_admin") == PolicyVerdict.ESCALATE
    assert spec.verdict_for_role("random") == PolicyVerdict.DENY
```

**Step 2: Run to verify it fails** -- `python -m unittest tests.test_catalog -v` -> FAIL (knowledge_base not registered).

**Step 3: Implement** -- create `knowledge_base.py` following `data_platform.py` shape:

```python
TARGET_SYSTEM = "knowledge_base"
_KB_ADMIN = ("kb_admin",)

SPECS = (
    ActionSpec(TARGET_SYSTEM, "rag_retrieve", RiskLevel.LOW,
               PolicyVerdict.ALLOW, PolicyVerdict.ALLOW, (), "Retrieve docs for a query."),
    ActionSpec(TARGET_SYSTEM, "rag_embed", RiskLevel.LOW,
               PolicyVerdict.ALLOW, PolicyVerdict.ALLOW, (), "Embed text into vectors."),
    ActionSpec(TARGET_SYSTEM, "rag_index", RiskLevel.MEDIUM,
               PolicyVerdict.ESCALATE, PolicyVerdict.DENY, _KB_ADMIN, "Index/ingest new docs."),
)
```
Add `"knowledge_base"` to `DOMAIN_MODULES`.

**Step 4: Run -> PASS.**

**Step 5: Commit** `feat(catalog): knowledge_base domain with rag_* actions`.

### Task 2: RagBackend protocol + data types

**Files:**
- Create: `recette/rag.py`
- Test: `tests/test_rag.py`

**Step 1: Failing test**

```python
def test_retrieved_doc_is_frozen_record(self):
    d = RetrievedDoc(doc_id="d1", score=2, text="hello")
    assert (d.doc_id, d.score, d.text) == ("d1", 2, "hello")
```

**Step 3: Implement** the dataclasses + Protocol in `recette/rag.py`:

```python
@dataclass(frozen=True)
class Document:
    doc_id: str
    text: str

@dataclass(frozen=True)
class RetrievedDoc:
    doc_id: str
    score: int        # integer score -> float-free decision path (R11/I4)
    text: str

class RagBackend(Protocol):
    def retrieve(self, query: str, *, k: int) -> list[RetrievedDoc]: ...
    def index(self, docs: list[Document]) -> int: ...   # returns count indexed
```

**Step 5: Commit** `feat(rag): RagBackend protocol + Document/RetrievedDoc`.

### Task 3: DeterministicRagBackend (lab default, I4)

**Files:** Modify `recette/rag.py`; Test `tests/test_rag.py`.

**Step 1: Failing tests**

```python
CORPUS = [Document("d1", "cats and dogs"), Document("d2", "dogs run fast"),
          Document("d3", "quantum physics")]

def test_retrieve_ranks_by_token_overlap(self):
    rag = DeterministicRagBackend(CORPUS)
    top = rag.retrieve("dogs", k=2)
    assert [d.doc_id for d in top] == ["d1", "d2"]  # both match "dogs"; tie-break by doc_id

def test_retrieve_is_deterministic_across_runs(self):
    rag = DeterministicRagBackend(CORPUS)
    assert rag.retrieve("dogs run", k=3) == rag.retrieve("dogs run", k=3)

def test_tie_break_is_stable_by_doc_id(self):
    rag = DeterministicRagBackend(CORPUS)
    # equal scores must order by doc_id ascending, never by insertion/hash
    ...

def test_index_appends_and_returns_count(self):
    rag = DeterministicRagBackend([])
    assert rag.index(CORPUS) == 3
```

**Step 3: Implement** deterministic lexical scoring: `score = count of query tokens present in doc` (integer), sort by `(-score, doc_id)`, slice `k`. No clock, no random, no float -> I4-safe.

**Step 5: Commit** `feat(rag): DeterministicRagBackend with stable lexical ranking`.

### Task 4: RealRagBackend (optional extra, R8, captured non-determinism)

**Files:** Modify `recette/rag.py`, `pyproject.toml` (add `[rag]` extra); Test `tests/test_rag.py`.

**Step 1: Failing tests** (offline, injected stub client like test_llm.py)

```python
def test_real_backend_missing_key_raises_naming_env_var(self):
    os.environ.pop("RAG_EMBEDDINGS_API_KEY", None)
    with self.assertRaises(RuntimeError) as ctx:
        RealRagBackend(model="text-embedding-3-small")
    assert "RAG_EMBEDDINGS_API_KEY" in str(ctx.exception)

def test_real_backend_retrieve_via_stub_client(self):
    client = _StubClient(embedding=[0, 1, 0])  # deterministic stub
    rag = RealRagBackend(model="m", client=client)
    rag.index([Document("d1", "x")])
    out = rag.retrieve("x", k=1)
    assert out[0].doc_id == "d1"
```

**Step 3: Implement** `RealRagBackend`: reads `RAG_EMBEDDINGS_API_KEY` (or accepts api_key/client), embeds via the injected `_PostClient`, stores vectors in-process (FAISS only under the `[rag]` extra; fall back to a pure-python cosine when faiss absent). Capture retrieved ids+scores so a replay re-reads them (I4). Secrets via env (R8), never logged.

`pyproject.toml`:
```toml
[project.optional-dependencies]
rag = ["faiss-cpu>=1.8"]
```

**Step 5: Commit** `feat(rag): RealRagBackend (embeddings + vector store, [rag] extra)`.

### Task 5: build_rag factory

**Files:** Modify `recette/rag.py`; Test `tests/test_rag.py`.

**Step 1: Failing test**

```python
def test_build_rag_deterministic(self):
    assert isinstance(build_rag("deterministic", corpus=CORPUS), DeterministicRagBackend)

def test_build_rag_real_threads_client(self):
    rag = build_rag("real", model="m", client=_StubClient())
    assert isinstance(rag, RealRagBackend)

def test_build_rag_unknown_raises(self):
    with self.assertRaises(ValueError):
        build_rag("bogus")
```

**Step 3: Implement** `build_rag(kind, *, corpus=None, model=None, client=None, api_key=None)` mirroring `build_llm`.

**Step 5: Commit** `feat(rag): build_rag factory`.

### Task 6: deterministic replay test (I4 gate)

**Files:** Test `tests/test_rag.py`.

Replay the same query stream twice + assert byte-identical results AND match a golden. Mirrors `determinism-replay.md`. Commit `test(rag): deterministic replay golden`.

### Phase 1 gates (run before closing)

```bash
.venv/bin/python -m unittest tests.test_rag tests.test_catalog
.venv/bin/ruff check recette/rag.py recette/platform/catalog/domains/knowledge_base.py tests/test_rag.py
.venv/bin/mypy recette/rag.py
.venv/bin/bandit -q -r recette/rag.py
```

---

## Phase 2 -- RAG test-agent corpus + external-tool recette (higher level)

- Extend `corpus/schemas/scenario.schema.json` to allow the rag_* action types.
- Author corpus agents under `corpus/agents/correct/` and `corpus/agents/incorrect/`:
  one positive (declares + does rag_retrieve in scope), one `capability_overreach`
  (declares retrieve-only, does rag_index), one `behavior_anomaly` (retrieves off-topic).
- Add `RagAdapter` protocol + `ReferenceRagAdapter` oracle in `recette/adapters.py`
  (mirrors DiscoveryAdapter/IdentificationAdapter). Ground-truth = invariants only
  (expected docs retrieved, relative ordering, determinism), never opaque scores.
- Scorecard: retrieval precision/recall + ordering correctness.
- CLI: `python -m recette rag --adapter reference|http`.
- Extend `test_each_negative_breaks_exactly_one_dimension`.

## Phase 3 -- Retrieval infra for real agents (higher level)

- Wire `rag_retrieve` into the real-agent loop (recette/agent.py) through a
  mediated proxy (I5); inject retrieved context into the next LLM turn.
- Retrieval is an audited side effect (`side_effect_hash`), captured for replay.

## Phase 4 -- Console /rag menu (higher level)

- New page `console/src/pages/rag/` + nav link in `App.tsx`.
- Knowledge-base view, RAG agents list, RAG recette scorecard, LogConsole.
- R16 contract gate: real fixtures + render-and-assert. Reuse `lib/` helpers.

---

## Post-implementation

Run `audit-pdca --fix` on each shipped phase (user-requested).
