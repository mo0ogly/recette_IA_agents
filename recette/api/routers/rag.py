"""RAG retrieval-quality recette endpoint for the console.

GET /rag/scorecard runs the deterministic retrieval recette over the
ground-truth eval file (corpus/rag/retrieval-eval.json) and returns the
scorecard. Read-only and deterministic (I4): no clock / random, the reference
backend ranks the seeded corpus the same way every call.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

from ...rag import DeterministicRagBackend, Document
from ...rag_eval import RagQueryTruth, ReferenceRagAdapter, judge_rag

router = APIRouter(prefix="/rag", tags=["rag"])

_EVAL_PATH = Path(__file__).resolve().parents[3] / "corpus" / "rag" / "retrieval-eval.json"


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
