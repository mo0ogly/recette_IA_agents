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
decision/replay path). Sessions are lost on API restart by design for now
(persistence is a tracked backlog item).
"""

from __future__ import annotations

import threading
from collections import OrderedDict, deque
from typing import Any

from ._timestamp import capture_timestamp

MAX_THREAD_MESSAGES = 40  # 20 turns (user + assistant)
MAX_INSIGHTS = 100
MAX_SESSIONS = 50


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


class AssistSessionStore:
    """Bounded LRU registry of assist sessions, keyed by client session id."""

    def __init__(self, max_sessions: int = MAX_SESSIONS) -> None:
        self._sessions: OrderedDict[str, AssistSession] = OrderedDict()
        self._max_sessions = max_sessions
        self._lock = threading.RLock()

    def get_or_create(self, session_id: str) -> AssistSession:
        with self._lock:
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
            session = self._sessions.get(session_id)
            if session is not None:
                self._sessions.move_to_end(session_id)
            return session

    def clear(self, session_id: str) -> None:
        """Drop one session's memory. Idempotent: unknown id is a no-op."""
        with self._lock:
            self._sessions.pop(session_id, None)

    def count(self) -> int:
        with self._lock:
            return len(self._sessions)
