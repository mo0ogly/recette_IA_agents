"""knowledge_base mock handler -- RAG retrieval + index management.

query_knowledge_base returns documents from the seeded corpus (corpus/rag/
knowledge_base.json), INCLUDING poisoned ones: the lab faithfully models a
polluted RAG so the recette can prove the gateway -- not the data source --
is what stops the induced action. Handlers are pure and deterministic: same
input -> identical response bytes (stable ids from sha256, no clock/random, I4).
"""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

_KB_PATH = Path(__file__).resolve().parents[3] / "corpus" / "rag" / "knowledge_base.json"

_ACTION_FIELDS: dict[str, dict[str, str]] = {
    "ingest_document": {"index_state": "document_ingested"},
    "update_retrieval_config": {"config_state": "updated"},
    "export_knowledge_base": {"export_state": "archive_built"},
    "delete_document": {"index_state": "document_removed"},
    "purge_index": {"index_state": "purged"},
}


@lru_cache(maxsize=1)
def _documents() -> tuple[dict, ...]:
    data = json.loads(_KB_PATH.read_text(encoding="utf-8"))
    return tuple(data["documents"])


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
    """Return a deterministic response dict, or None when action is unknown."""
    material = f"knowledge_base:{action_type}:{resource}:{json.dumps(payload, sort_keys=True)}"
    result_id = hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]
    response: dict = {
        "action": action_type,
        "resource": resource,
        "status": "simulated",
        "result_id": result_id,
    }
    if action_type == "query_knowledge_base":
        response["documents"] = _retrieve(resource)
        return response
    extra = _ACTION_FIELDS.get(action_type)
    if extra is None:
        return None
    response.update(extra)
    return response
