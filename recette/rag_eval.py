"""RAG retrieval-quality recette: judge a retrieval tool against ground truth.

Mirrors the discovery / identification recette pattern, but for RAG retrieval.
A `RagAdapter` is any tool that returns ranked doc ids for a query; the
`ReferenceRagAdapter` wraps a `RagBackend` (recette/rag.py) as the
correct-by-reference oracle.

Ground truth is INVARIANT, never the opaque internal scores: it states which
docs are relevant for a query and, optionally, which one should rank first. A
real tool with completely different scoring still passes if it surfaces the
right docs in a sane order. PASS/FAIL is a deterministic set+order comparison
(I4); precision / recall are reported as fractions for the scorecard only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .rag import RagBackend


@dataclass(frozen=True)
class RagQueryTruth:
    """Expected retrieval for one query.

    relevant_ids: the doc ids that SHOULD be retrieved (order-insensitive set).
    top_id: if set, the id that MUST rank first. None means order is not judged.
    """

    query: str
    relevant_ids: tuple[str, ...]
    top_id: str | None = None


@runtime_checkable
class RagAdapter(Protocol):
    def retrieve(self, query: str, *, k: int) -> list[str]: ...


class ReferenceRagAdapter:
    """Correct-by-reference adapter: ranked doc ids from a RagBackend.

    This is both a working oracle and the template an external RAG tool's
    adapter must satisfy (return ranked doc ids, most relevant first)."""

    def __init__(self, backend: RagBackend) -> None:
        self._backend = backend

    def retrieve(self, query: str, *, k: int) -> list[str]:
        return [doc.doc_id for doc in self._backend.retrieve(query, k=k)]


@dataclass(frozen=True)
class RagQueryResult:
    query: str
    retrieved: tuple[str, ...]
    precision: float
    recall: float
    top_ok: bool
    passed: bool


@dataclass(frozen=True)
class RagScorecard:
    results: tuple[RagQueryResult, ...]

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed_count(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def all_passed(self) -> bool:
        return all(r.passed for r in self.results) and bool(self.results)

    @property
    def mean_precision(self) -> float:
        return sum(r.precision for r in self.results) / self.total if self.results else 0.0

    @property
    def mean_recall(self) -> float:
        return sum(r.recall for r in self.results) / self.total if self.results else 0.0

    def render(self) -> str:
        lines = [
            "RAG retrieval recette",
            f"  queries     : {self.total}",
            f"  passed      : {self.passed_count}/{self.total}",
            f"  mean prec.  : {self.mean_precision:.2f}",
            f"  mean recall : {self.mean_recall:.2f}",
        ]
        for r in self.results:
            verdict = "PASS" if r.passed else "FAIL"
            lines.append(
                f"  [{verdict}] {r.query!r} -> {list(r.retrieved)} "
                f"(p={r.precision:.2f} r={r.recall:.2f} top_ok={r.top_ok})"
            )
        return "\n".join(lines)


def _score_query(retrieved: list[str], truth: RagQueryTruth) -> RagQueryResult:
    relevant = set(truth.relevant_ids)
    got = list(retrieved)
    hit = [d for d in got if d in relevant]
    precision = len(hit) / len(got) if got else 0.0
    recall = len(set(hit)) / len(relevant) if relevant else 1.0
    top_ok = truth.top_id is None or (len(got) > 0 and got[0] == truth.top_id)
    # PASS = every relevant doc surfaced AND the required top doc ranked first.
    passed = relevant.issubset(set(got)) and top_ok
    return RagQueryResult(
        query=truth.query,
        retrieved=tuple(got),
        precision=precision,
        recall=recall,
        top_ok=top_ok,
        passed=passed,
    )


def judge_rag(adapter: RagAdapter, truths: list[RagQueryTruth], *, k: int) -> RagScorecard:
    """Run every ground-truth query through the adapter and score it. Deterministic."""
    results = tuple(_score_query(adapter.retrieve(t.query, k=k), t) for t in truths)
    return RagScorecard(results=results)
