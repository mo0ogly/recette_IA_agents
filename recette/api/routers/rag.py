"""RAG retrieval-quality recette endpoint for the console.

GET /rag/scorecard runs the deterministic retrieval recette over the
ground-truth eval file (corpus/rag/retrieval-eval.json) and returns the
scorecard. Read-only and deterministic (I4): no clock / random, the reference
backend ranks the seeded corpus the same way every call.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response

from ...rag import DeterministicRagBackend, Document
from ...rag_eval import RagQueryTruth, ReferenceRagAdapter, judge_rag
from ...rag_store import KnowledgeBaseError

router = APIRouter(prefix="/rag", tags=["rag"])

_EVAL_PATH = Path(__file__).resolve().parents[3] / "corpus" / "rag" / "retrieval-eval.json"


def _kb(request: Request):  # type: ignore[no-untyped-def]
    return request.app.state.kb_store


@router.get("/scorecard")
def rag_scorecard(k: int = 5) -> dict:
    """Run the retrieval recette and return the scorecard (per-query + aggregates)."""
    try:
        spec = json.loads(_EVAL_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=f"eval file unreadable: {exc}") from exc

    corpus = [Document(doc_id=d["doc_id"], text=d["text"]) for d in spec["corpus"]]
    truths = [
        RagQueryTruth(
            query=q["query"],
            relevant_ids=tuple(q["relevant_ids"]),
            top_id=q.get("top_id"),
        )
        for q in spec["queries"]
    ]
    card = judge_rag(ReferenceRagAdapter(DeterministicRagBackend(corpus)), truths, k=k)
    return {
        "total": card.total,
        "passed": card.passed_count,
        "all_passed": card.all_passed,
        "mean_precision": round(card.mean_precision, 4),
        "mean_recall": round(card.mean_recall, 4),
        "results": [
            {
                "query": r.query,
                "retrieved": list(r.retrieved),
                "precision": round(r.precision, 4),
                "recall": round(r.recall, 4),
                "top_ok": r.top_ok,
                "passed": r.passed,
            }
            for r in card.results
        ],
    }


# --- Operator knowledge-base CRUD (off the agent path, I2-safe) ---------------
# These routes PREPARE the recette: an operator inspects/seeds/poisons/resets the
# knowledge base. They are NOT agent actions -- an agent that wants to mutate the
# index still flows through the gateway (ingest_document escalates). Never wire a
# knowledge-base mutation onto the agent /actions/execute path.


@router.get("/documents")
def list_kb_documents(request: Request) -> dict:
    """List the current knowledge base (baseline + any applied scenario)."""
    docs = _kb(request).documents()
    return {
        "documents": [
            {
                "id": d["id"],
                "title": d["title"],
                "tags": d["tags"],
                "poisoned": d["poisoned"],
                "threat": d.get("threat"),
            }
            for d in docs
        ]
    }


@router.post("/documents", status_code=201)
def add_kb_document(request: Request, document: dict[str, Any]) -> dict:
    try:
        return _kb(request).add(document)
    except KnowledgeBaseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/documents/{doc_id}", status_code=204)
def delete_kb_document(request: Request, doc_id: str) -> Response:
    try:
        _kb(request).delete(doc_id)
    except KnowledgeBaseError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=204)


@router.post("/reset")
def reset_kb(request: Request) -> dict:
    """Restore the clean baseline (un-poison). Deterministic (I4)."""
    count = _kb(request).reset()
    return {"reset": True, "documents": count}


@router.get("/scenarios")
def list_rag_scenarios(request: Request) -> dict:
    return {"scenarios": _kb(request).list_scenarios()}


@router.post("/scenario/{name}/apply", status_code=201)
def apply_rag_scenario(request: Request, name: str) -> dict:
    try:
        injected = _kb(request).apply_scenario(name)
    except KnowledgeBaseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"applied": name, "injected": [d["id"] for d in injected]}
