"""In-memory per-session memory for the assist copilot (Copilote IA).

One ``AssistSession`` per console browser session (the client mints a UUID and
keeps it in localStorage). Each session holds the two memories the copilot
consolidates in the left dock:

- ``thread``: the multi-turn chat, bounded to the last ``MAX_THREAD_MESSAGES``
  entries (20 user+assistant turns) -- the replay window sent back to the LLM;
- ``insights``: the contextual-help journal, bounded to ``MAX_INSIGHTS``.

The registry itself is bounded (``MAX_SESSIONS``, LRU eviction) so an
unauthenticated dev API cannot grow without limit.

Operational, diagnostic-path state: ids are per-session sequences and
timestamps are wall-clock captures, like the ephemeral ``Run`` records in
``recette.api.runs`` (documented I4 stance: this never enters the
decision/replay path).

Persistence: optional gitignored runtime sidecar
(``data/assist_sessions.runtime.json``). Every mutation snapshots the whole
registry (atomic temp + os.replace); startup rehydrates lazily. Fail-safe: a
missing/corrupt sidecar reads as an empty registry, and a write failure never
breaks the assist endpoints (the memory keeps working in-process).
"""

from __future__ import annotations

import json
import logging
import os
import threading
from collections import OrderedDict, deque
from pathlib import Path
from typing import Any

from ._timestamp import capture_timestamp

_log = logging.getLogger(__name__)

MAX_THREAD_MESSAGES = 40  # 20 turns (user + assistant)
MAX_INSIGHTS = 100
MAX_SESSIONS = 50


def default_sessions_path() -> Path:
    env = os.environ.get("INSPECT_IA_AGENTS_ASSIST_SESSIONS_PATH")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent.parent / "data" / "assist_sessions.runtime.json"


class AssistSession:
    """Chat thread + insights journal for one console session."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.thread: deque[dict[str, Any]] = deque(maxlen=MAX_THREAD_MESSAGES)
        self.insights: deque[dict[str, Any]] = deque(maxlen=MAX_INSIGHTS)
        self._message_seq = 0
        self._insight_seq = 0

    def add_message(
        self, *, role: str, content: str, source: str, model: str | None = None
    ) -> dict[str, Any]:
        self._message_seq += 1
        entry = {
            "id": f"m-{self._message_seq}",
            "role": role,
            "content": content,
            "source": source,
            "model": model,
            "created_at": capture_timestamp(),
        }
        self.thread.append(entry)
        return entry

    def add_insight(
        self, *, topic: str, label: str, answer: str, model: str | None = None
    ) -> dict[str, Any]:
        self._insight_seq += 1
        entry = {
            "id": f"i-{self._insight_seq}",
            "topic": topic,
            "label": label,
            "answer": answer,
            "model": model,
            "created_at": capture_timestamp(),
        }
        self.insights.append(entry)
        return entry

    def thread_list(self) -> list[dict[str, Any]]:
        return list(self.thread)

    def insights_list(self) -> list[dict[str, Any]]:
        return list(self.insights)

    def to_snapshot(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "thread": list(self.thread),
            "insights": list(self.insights),
            "message_seq": self._message_seq,
            "insight_seq": self._insight_seq,
        }

    @classmethod
    def from_snapshot(cls, snapshot: dict[str, Any]) -> AssistSession:
        session = cls(str(snapshot.get("session_id", "")))
        for entry in snapshot.get("thread") or []:
            if isinstance(entry, dict):
                session.thread.append(entry)
        for entry in snapshot.get("insights") or []:
            if isinstance(entry, dict):
                session.insights.append(entry)
        session._message_seq = int(snapshot.get("message_seq", len(session.thread)))
        session._insight_seq = int(snapshot.get("insight_seq", len(session.insights)))
        return session


class AssistSessionStore:
    """Bounded LRU registry of assist sessions, keyed by client session id.

    When ``path`` is set (the default in the app), the registry is snapshotted
    to a gitignored runtime sidecar on every mutation via ``persist()`` --
    called by the router AFTER a chat/help/clear mutation -- and rehydrated
    lazily on first access. ``path=None`` keeps the store purely in-memory
    (unit tests that do not care about persistence).
    """

    def __init__(self, max_sessions: int = MAX_SESSIONS, path: Path | str | None = None) -> None:
        self._sessions: OrderedDict[str, AssistSession] = OrderedDict()
        self._max_sessions = max_sessions
        self._lock = threading.RLock()
        self._path = Path(path) if path is not None else None
        self._loaded = self._path is None

    def _ensure_loaded(self) -> None:
        """Lazy one-shot rehydration. Fail-safe: corrupt/missing file = empty."""
        if self._loaded:
            return
        self._loaded = True
        assert self._path is not None
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            _log.warning("assist sessions sidecar unreadable, starting empty reason=%s", exc)
            return
        for snapshot in (data.get("sessions") if isinstance(data, dict) else None) or []:
            if isinstance(snapshot, dict) and snapshot.get("session_id"):
                session = AssistSession.from_snapshot(snapshot)
                self._sessions[session.session_id] = session
        while len(self._sessions) > self._max_sessions:
            self._sessions.popitem(last=False)

    def persist(self) -> None:
        """Snapshot the registry to the sidecar (atomic). Never raises."""
        if self._path is None:
            return
        with self._lock:
            payload = {"sessions": [s.to_snapshot() for s in self._sessions.values()]}
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(self._path.suffix + ".tmp")
            tmp.write_text(
                json.dumps(payload, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            os.replace(tmp, self._path)
        except OSError as exc:
            # A persistence failure must never take the assist endpoints down.
            _log.warning("assist sessions persist failed reason=%s", exc)

    def get_or_create(self, session_id: str) -> AssistSession:
        with self._lock:
            self._ensure_loaded()
            session = self._sessions.get(session_id)
            if session is None:
                session = AssistSession(session_id)
                self._sessions[session_id] = session
                while len(self._sessions) > self._max_sessions:
                    self._sessions.popitem(last=False)
            else:
                self._sessions.move_to_end(session_id)
            return session

    def get(self, session_id: str) -> AssistSession | None:
        with self._lock:
            self._ensure_loaded()
            session = self._sessions.get(session_id)
            if session is not None:
                self._sessions.move_to_end(session_id)
            return session

    def clear(self, session_id: str) -> None:
        """Drop one session's memory. Idempotent: unknown id is a no-op."""
        with self._lock:
            self._ensure_loaded()
            self._sessions.pop(session_id, None)

    def count(self) -> int:
        with self._lock:
            self._ensure_loaded()
            return len(self._sessions)
