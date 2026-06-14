"""Retrieval infra (P3): turn a query into an LLM-injectable context block.

A real agent calls `retrieve_context` to fetch supporting documents from a
`RagBackend` before its next LLM turn (proxy-mediated retrieval, I5). The result
is deterministic given a deterministic backend and carries a content hash so the
injected context is auditable and replayable (I1): the same query + corpus
always produce the same block and the same hash.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .rag import RagBackend, RetrievedDoc


@dataclass(frozen=True)
class RetrievedContext:
    """The outcome of one retrieval: the docs, the formatted block handed to the
    LLM, and a stable hash of that block for the audit trail (I1)."""

    query: str
    docs: tuple[RetrievedDoc, ...]
    text: str
    context_hash: str


def _format_block(query: str, docs: tuple[RetrievedDoc, ...]) -> str:
    if not docs:
        return f"[retrieved 0 documents for: {query}]"
    lines = [f"[retrieved {len(docs)} document(s) for: {query}]"]
    for doc in docs:
        lines.append(f"- ({doc.doc_id}) {doc.text}")
    return "\n".join(lines)


def retrieve_context(backend: RagBackend, query: str, *, k: int = 3) -> RetrievedContext:
    """Retrieve up to k docs and format them as a context block for the next LLM turn.

    Deterministic: ordering comes from the backend (stable), the hash is sha256 of
    the block. No clock / random (I4)."""
    docs = tuple(backend.retrieve(query, k=k))
    block = _format_block(query, docs)
    context_hash = hashlib.sha256(block.encode("utf-8")).hexdigest()[:16]
    return RetrievedContext(query=query, docs=docs, text=block, context_hash=context_hash)
