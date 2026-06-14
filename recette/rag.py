"""RAG backends: retrieval over a document corpus.

Mirrors recette/llm.py. A `RagBackend` Protocol has two implementations:

- `DeterministicRagBackend`: the lab default. Lexical overlap scoring with a
  stable tie-break by doc id, no clock / random / hard dependency. I4-safe:
  the same corpus + query always yields the same ranking.
- `RealRagBackend`: embeddings via a provider through an injectable HTTP client
  (offline-testable like the LLM backends). The non-deterministic similarity is
  reduced to an integer score so the ordering is stable and capturable for
  replay (I4). The real vector store is the optional `[rag]` extra; absent it a
  pure-python cosine is used. Secrets come from the environment (R8).

`build_rag(kind, ...)` mirrors `build_llm`.
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Document:
    """A corpus document to index."""

    doc_id: str
    text: str


@dataclass(frozen=True)
class RetrievedDoc:
    """One retrieval hit. `score` is an integer so the ranking stays float-free
    and reproducible (R11/I4): the deterministic backend scores by token
    overlap, the real backend scales cosine similarity into an integer."""

    doc_id: str
    score: int
    text: str


@runtime_checkable
class RagBackend(Protocol):
    def index(self, docs: list[Document]) -> int: ...
    def retrieve(self, query: str, *, k: int) -> list[RetrievedDoc]: ...


# --- HTTP transport shape (matches recette._http_client.StdlibHttpClient) ----------------


class _Response(Protocol):
    def raise_for_status(self) -> None: ...
    def json(self) -> object: ...


class _PostClient(Protocol):
    def post(self, path: str, json: dict | None = ...) -> _Response: ...


_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    """Lowercase alphanumeric tokens, deduplicated."""
    return set(_TOKEN.findall(text.lower()))


# --- deterministic lab backend -----------------------------------------------------------


class DeterministicRagBackend:
    """Lab default: rank docs by the count of distinct query tokens they contain.

    Ordering is `(-score, doc_id)` so ties break stably by doc id, never by
    insertion order or hashing -- the property that makes retrieval replayable.
    """

    def __init__(self, corpus: list[Document] | None = None) -> None:
        self._docs: list[Document] = []
        if corpus:
            self.index(corpus)

    def index(self, docs: list[Document]) -> int:
        self._docs.extend(docs)
        return len(docs)

    def retrieve(self, query: str, *, k: int) -> list[RetrievedDoc]:
        q = _tokens(query)
        hits: list[RetrievedDoc] = []
        for doc in self._docs:
            score = len(q & _tokens(doc.text))
            if score > 0:
                hits.append(RetrievedDoc(doc_id=doc.doc_id, score=score, text=doc.text))
        hits.sort(key=lambda d: (-d.score, d.doc_id))
        return hits[:k]


# --- real backend (embeddings + vector store) --------------------------------------------


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


class RealRagBackend:
    """Embeddings-backed retrieval. Embeds via an injected HTTP client (OpenAI
    embeddings wire by default). Cosine similarity is scaled to an integer score
    so the ranking is stable and capturable (I4). Key from `RAG_EMBEDDINGS_API_KEY`
    unless a client/api_key is passed (R8)."""

    ENV_KEY = "RAG_EMBEDDINGS_API_KEY"
    BASE_URL = "https://api.openai.com"
    EMBED_PATH = "/v1/embeddings"

    def __init__(
        self,
        *,
        model: str,
        client: _PostClient | None = None,
        api_key: str | None = None,
    ) -> None:
        self._model = model
        if client is None:
            key = api_key or os.environ.get(self.ENV_KEY)
            if not key:
                raise RuntimeError(f"{self.ENV_KEY} not set (or pass client/api_key)")
            from ._http_client import StdlibHttpClient

            client = StdlibHttpClient(self.BASE_URL, headers={"Authorization": f"Bearer {key}"})
        self._client = client
        self._vectors: list[tuple[Document, list[float]]] = []

    def _embed(self, text: str) -> list[float]:
        resp = self._client.post(self.EMBED_PATH, json={"model": self._model, "input": text})
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict):
            raise RuntimeError("embeddings response is not an object")
        rows = data.get("data")
        if not isinstance(rows, list) or not rows:
            raise RuntimeError("embeddings response has no data")
        embedding = rows[0].get("embedding")
        if not isinstance(embedding, list):
            raise RuntimeError("embeddings response has no embedding")
        return [float(x) for x in embedding]

    def index(self, docs: list[Document]) -> int:
        for doc in docs:
            self._vectors.append((doc, self._embed(doc.text)))
        return len(docs)

    def retrieve(self, query: str, *, k: int) -> list[RetrievedDoc]:
        qv = self._embed(query)
        hits: list[RetrievedDoc] = []
        for doc, vec in self._vectors:
            score = int(round(_cosine(qv, vec) * 1000))
            hits.append(RetrievedDoc(doc_id=doc.doc_id, score=score, text=doc.text))
        hits.sort(key=lambda d: (-d.score, d.doc_id))
        return hits[:k]


# --- factory -----------------------------------------------------------------------------

_KINDS = ("deterministic", "real")


def build_rag(
    kind: str,
    *,
    corpus: list[Document] | None = None,
    model: str | None = None,
    client: _PostClient | None = None,
    api_key: str | None = None,
) -> RagBackend:
    """Construct a RAG backend by name, mirroring `build_llm`.

    `deterministic` takes an optional starting corpus; `real` takes a model and
    resolves its key from api_key or the env var (R8) unless a client is injected.
    """
    if kind == "deterministic":
        return DeterministicRagBackend(corpus)
    if kind == "real":
        if model is None and client is None:
            raise ValueError("real backend requires model (or an injected client)")
        return RealRagBackend(model=model or "", client=client, api_key=api_key)
    raise ValueError(f"unknown rag kind {kind!r}; known: {', '.join(_KINDS)}")
