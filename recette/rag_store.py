"""Operator knowledge-base store for the RAG poisoning recette.

This is a BANC-DE-TEST tool, OFF the agent path: it lets a recette operator view,
insert, delete documents, apply a named poison scenario, and RESET to the clean
baseline. It is NOT an agent action -- an agent that wants to mutate the index
still goes through the gateway (ingest_document escalates, purge_index denies, I2).
Exposing this store on operator routes never creates a path for an agent to mutate
the knowledge base without mediation.

State model (baseline-backed, deterministic I4):
- the baseline is corpus/rag/knowledge_base.json (committed source of truth);
- a single in-memory document list is seeded from it and shared with the lab
  handler (recette/lab/domains/knowledge_base.py) so a live agent query reflects
  the current state (baseline + applied scenario);
- reset() reloads the baseline exactly -> the same bytes every time, no clock,
  no random.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_BASELINE_PATH = _REPO_ROOT / "corpus" / "rag" / "knowledge_base.json"
_SCENARIOS_DIR = _REPO_ROOT / "corpus" / "rag" / "scenarios"

_REQUIRED_KEYS = ("id", "title", "content", "poisoned", "tags")
_POISON_KEYS = ("injected_action", "injected_target_system", "injected_expect", "threat")
# Scenario names AND document ids map to a slug shape (same as the schema's
# `name`/`id` pattern). For names it forbids path traversal ("../knowledge_base",
# absolute paths); for ids it is defence in depth -- an id touches no file path,
# but enforcing the schema shape at the store keeps inserts coherent with the
# committed corpus and rejects stray identifiers early.
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")

# Shared in-memory knowledge base: seeded lazily from the baseline, mutated by the
# store, read by the lab handler. None means "not yet seeded".
_LIVE: list[dict] | None = None


class KnowledgeBaseError(ValueError):
    """Invalid document, duplicate id, unknown id, or unknown scenario."""


def _load_baseline(path: Path = _BASELINE_PATH) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data["documents"])


def live_documents() -> list[dict]:
    """Return the shared mutable KB, seeding it from the baseline on first use."""
    global _LIVE
    if _LIVE is None:
        _LIVE = copy.deepcopy(_load_baseline())
    return _LIVE


def _validate(doc: dict) -> dict:
    missing = [k for k in _REQUIRED_KEYS if k not in doc]
    if missing:
        raise KnowledgeBaseError(f"document missing keys: {missing}")
    if not isinstance(doc["id"], str) or not doc["id"]:
        raise KnowledgeBaseError("document id must be a non-empty string")
    if not _NAME_RE.fullmatch(doc["id"]):
        raise KnowledgeBaseError(f"document id must match {_NAME_RE.pattern}: {doc['id']!r}")
    if not isinstance(doc["poisoned"], bool):
        raise KnowledgeBaseError("'poisoned' must be a boolean")
    if not isinstance(doc["tags"], list):
        raise KnowledgeBaseError("'tags' must be a list")
    if doc["poisoned"]:
        missing_poison = [k for k in _POISON_KEYS if k not in doc]
        if missing_poison:
            raise KnowledgeBaseError(f"poisoned document missing keys: {missing_poison}")
    return doc


class KnowledgeBaseStore:
    """Operator CRUD over the shared in-memory knowledge base."""

    def __init__(
        self, *, baseline_path: Path = _BASELINE_PATH, scenarios_dir: Path = _SCENARIOS_DIR
    ):
        self._baseline_path = baseline_path
        self._scenarios_dir = scenarios_dir
        # Touch the shared state so the store and the lab handler agree from start.
        live_documents()

    def documents(self) -> list[dict]:
        return [copy.deepcopy(d) for d in live_documents()]

    def get(self, doc_id: str) -> dict | None:
        for doc in live_documents():
            if doc["id"] == doc_id:
                return copy.deepcopy(doc)
        return None

    def add(self, doc: dict) -> dict:
        _validate(doc)
        docs = live_documents()
        if any(d["id"] == doc["id"] for d in docs):
            raise KnowledgeBaseError(f"duplicate document id: {doc['id']!r}")
        docs.append(copy.deepcopy(doc))
        return copy.deepcopy(doc)

    def delete(self, doc_id: str) -> None:
        docs = live_documents()
        for i, doc in enumerate(docs):
            if doc["id"] == doc_id:
                del docs[i]
                return
        raise KnowledgeBaseError(f"unknown document id: {doc_id!r}")

    def reset(self) -> int:
        """Restore the clean baseline exactly. Returns the document count."""
        global _LIVE
        _LIVE = copy.deepcopy(_load_baseline(self._baseline_path))
        return len(_LIVE)

    def list_scenarios(self) -> list[str]:
        if not self._scenarios_dir.is_dir():
            return []
        return sorted(
            p.stem for p in self._scenarios_dir.glob("*.json") if p.name != "scenario.schema.json"
        )

    def apply_scenario(self, name: str) -> list[dict]:
        """Inject every document of a named scenario. Returns the injected docs."""
        if not _NAME_RE.fullmatch(name):
            raise KnowledgeBaseError(f"invalid scenario name: {name!r}")
        path = self._scenarios_dir / f"{name}.json"
        # Defence in depth: the resolved path must stay inside the scenarios dir.
        if path.resolve().parent != self._scenarios_dir.resolve() or not path.is_file():
            raise KnowledgeBaseError(f"unknown scenario: {name!r}")
        spec = json.loads(path.read_text(encoding="utf-8"))
        injected = [self.add(doc) for doc in spec["documents"]]
        return injected
