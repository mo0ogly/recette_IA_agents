"""knowledge_base mock handler -- RAG retrieval + index management.

query_knowledge_base returns documents from the seeded corpus (corpus/rag/
knowledge_base.json), INCLUDING poisoned ones: the lab faithfully models a
polluted RAG so the recette can prove the gateway -- not the data source --
is what stops the induced action. The index-management actions return realistic
deterministic objects. Handlers are pure and deterministic: same input ->
identical bytes (stable ids from sha256, no clock/random/state, I4). See
``_realism`` for the shared primitives and the validation contract.
"""

from __future__ import annotations

from ...rag_store import live_documents
from ._realism import LabActionError, coerce_positive_number, derived_int, digest, envelope, ref


def _documents() -> tuple[dict, ...]:
    """Current shared knowledge base (baseline + any applied scenario)."""
    return tuple(live_documents())


def _retrieve(query: str) -> list[dict]:
    """Deterministic retrieval: documents whose tags/title/content match the query
    term, else the whole base. Poisoned documents are returned like any other."""
    q = query.lower()
    hits = [
        {"id": d["id"], "title": d["title"], "content": d["content"], "poisoned": d["poisoned"]}
        for d in _documents()
        if q in d["title"].lower() or q in d["content"].lower() or q in " ".join(d["tags"]).lower()
    ]
    if hits:
        return hits
    return [
        {"id": d["id"], "title": d["title"], "content": d["content"], "poisoned": d["poisoned"]}
        for d in _documents()
    ]


def handle(action_type: str, resource: str, payload: dict) -> dict | None:
    """Return a realistic deterministic response, ``None`` for an unknown action,
    or raise ``LabActionError`` for a known action with invalid input."""
    dig = digest("knowledge_base", action_type, resource, payload)
    base = envelope(action_type, resource, dig)

    if action_type == "query_knowledge_base":
        docs = _retrieve(resource)
        return {**base, "status": "ok", "match_count": len(docs), "documents": docs}
    if action_type == "ingest_document":
        return {
            **base,
            "status": "ingested",
            "document_id": ref("doc_", dig),
            "index": "main",
            "chunks": derived_int(dig, 1, 200),
        }
    if action_type == "update_retrieval_config":
        top_k = 5
        if "top_k" in payload:
            value = coerce_positive_number(payload["top_k"])
            if value is None:
                raise LabActionError(422, f"invalid top_k {payload['top_k']!r}")
            top_k = int(value)
        return {**base, "status": "updated", "config": resource, "top_k": top_k}
    if action_type == "export_knowledge_base":
        return {
            **base,
            "status": "exported",
            "export_id": ref("exp_", dig),
            "document_count": len(_documents()),
        }
    if action_type == "delete_document":
        return {**base, "status": "deleted", "document": resource, "deleted": True}
    if action_type == "purge_index":
        return {
            **base,
            "status": "purged",
            "index": resource or "main",
            "removed_count": len(_documents()),
        }
    return None
