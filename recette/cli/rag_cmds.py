"""RAG CLI commands: retrieval-quality recette and knowledge-base CRUD."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _cmd_rag(eval_path: str, k: int) -> int:
    """RAG retrieval-quality recette: judge a retrieval tool against ground truth."""
    from ..rag import DeterministicRagBackend, Document
    from ..rag_eval import RagQueryTruth, ReferenceRagAdapter, judge_rag

    spec = json.loads(Path(eval_path).read_text(encoding="utf-8"))
    corpus = [Document(doc_id=d["doc_id"], text=d["text"]) for d in spec["corpus"]]
    truths = [
        RagQueryTruth(
            query=q["query"],
            relevant_ids=tuple(q["relevant_ids"]),
            top_id=q.get("top_id"),
        )
        for q in spec["queries"]
    ]
    adapter = ReferenceRagAdapter(DeterministicRagBackend(corpus))
    scorecard = judge_rag(adapter, truths, k=k)
    print(scorecard.render())
    return 0 if scorecard.all_passed else 1


def _cmd_rag_kb(action: str, doc_path: str | None, doc_id: str | None, scenario: str | None) -> int:
    """Operator knowledge-base CRUD: list/add/del/reset/apply/scenarios."""
    from ..rag_store import KnowledgeBaseError, KnowledgeBaseStore

    store = KnowledgeBaseStore()
    try:
        if action == "list":
            for d in store.documents():
                flag = f"  [poison:{d.get('threat')}]" if d["poisoned"] else ""
                print(f"  {d['id']:28} {d['title']}{flag}")
            return 0
        if action == "scenarios":
            for name in store.list_scenarios():
                print(f"  {name}")
            return 0
        if action == "reset":
            print(f"reset -> baseline ({store.reset()} documents)")
            return 0
        if action == "apply":
            if not scenario:
                print("apply requires --scenario", file=sys.stderr)
                return 2
            injected = store.apply_scenario(scenario)
            print(f"applied {scenario}: injected {[d['id'] for d in injected]}")
            return 0
        if action == "add":
            if not doc_path:
                print("add requires --doc <file.json>", file=sys.stderr)
                return 2
            doc = json.loads(Path(doc_path).read_text(encoding="utf-8"))
            print(f"added {store.add(doc)['id']}")
            return 0
        if action == "del":
            if not doc_id:
                print("del requires --id", file=sys.stderr)
                return 2
            store.delete(doc_id)
            print(f"deleted {doc_id}")
            return 0
    except KnowledgeBaseError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"unknown rag-kb action: {action}", file=sys.stderr)
    return 2
