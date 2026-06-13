"""Content-addressed LLM call cache -- cheap, reproducible live runs (I4).

Same intent as langwatch/scenario's cache (joblib Memory keyed by the scenario +
the call arguments), but dependency-free: a ``CachingLlm`` wraps ANY ``LlmBackend``
and keys each decision on a stable digest of (namespace, system, history, tools).
On a hit it returns the stored ``LlmDecision`` without touching the network, so a
live Groq run is paid for once and then reproduces for free across every runner.

This is complementary to ``ReplayLlm``: ReplayLlm replays a recorded decision
SEQUENCE positionally (the exact run), while the cache is keyed by the call INPUTS
(content-addressed), so it survives reordering and is shared across runs.

The cache file is a plain JSON object {key: decision}. Writes are atomic. Default
location: AGENTRAIL_LLM_CACHE_DIR or ~/.agentrail/llm-cache; a key is never logged.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from .llm import LlmBackend, LlmDecision, Message, ToolSpec


def default_cache_path() -> Path:
    base = os.environ.get("AGENTRAIL_LLM_CACHE_DIR") or str(
        Path.home() / ".agentrail" / "llm-cache"
    )
    return Path(base) / "decisions.json"


def _decision_to_dict(d: LlmDecision) -> dict:
    return {"kind": d.kind, "tool_name": d.tool_name, "tool_args": d.tool_args, "text": d.text}


def _decision_from_dict(d: dict) -> LlmDecision:
    return LlmDecision(
        kind=d["kind"],
        tool_name=d.get("tool_name"),
        tool_args=d.get("tool_args", {}) or {},
        text=d.get("text", ""),
    )


def call_key(namespace: str, system: str, history: list[Message], tools: list[ToolSpec]) -> str:
    """Stable digest of one LLM call's inputs (sorted, canonical JSON)."""
    payload = {
        "namespace": namespace,
        "system": system,
        "history": [
            {"role": m.role, "content": m.content, "tool_name": m.tool_name} for m in history
        ],
        "tools": [
            {"name": t.name, "description": t.description, "parameters": t.parameters}
            for t in tools
        ],
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


class LlmCache:
    """A JSON-file-backed map {call_key: LlmDecision}."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_cache_path()
        self._data: dict[str, dict] = {}
        if self.path.is_file():
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                self._data = {}

    def get(self, key: str) -> LlmDecision | None:
        row = self._data.get(key)
        return _decision_from_dict(row) if row is not None else None

    def put(self, key: str, decision: LlmDecision) -> None:
        self._data[key] = _decision_to_dict(decision)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(self._data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)


class CachingLlm:
    """Wraps a backend; returns a cached decision on an input match, else calls
    the inner backend and records it. Persists on each new miss when autosave."""

    def __init__(
        self,
        inner: LlmBackend,
        *,
        cache: LlmCache | None = None,
        namespace: str = "",
        autosave: bool = True,
    ) -> None:
        self._inner = inner
        self._cache = cache if cache is not None else LlmCache()
        self._namespace = namespace
        self._autosave = autosave
        self.hits = 0
        self.misses = 0

    def decide(self, *, system: str, history: list[Message], tools: list[ToolSpec]) -> LlmDecision:
        key = call_key(self._namespace, system, history, tools)
        cached = self._cache.get(key)
        if cached is not None:
            self.hits += 1
            return cached
        decision = self._inner.decide(system=system, history=history, tools=tools)
        self._cache.put(key, decision)
        self.misses += 1
        if self._autosave:
            self._cache.save()
        return decision
