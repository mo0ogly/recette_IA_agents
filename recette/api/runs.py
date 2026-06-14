"""U1 RunManager: in-memory runs executed in worker threads, emitting event frames.

A run's frames are buffered on the Run (so a late WebSocket subscriber can replay them)
and pushed live to any attached asyncio subscriber queues (the WebSocket bridge).
Run ids are uuid4 — operational identifiers, not recette ground-truth artifacts.
"""

from __future__ import annotations

import asyncio
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

Runner = Callable[[dict, Callable[[str, dict], None], Callable[[], bool]], None]
_TERMINAL = {"completed", "failed", "stopped"}


@dataclass
class Run:
    id: str
    kind: str
    params: dict
    # Wall-clock creation time for the operator UI. Like the uuid4 id, this is
    # operational metadata -- it is NOT an AgentActionEvent field and never
    # enters the decision/replay path (I4 governs the event stream, not the
    # ephemeral run record).
    created_at: str = ""
    status: str = "pending"
    events: list[dict] = field(default_factory=list)
    error: str | None = None
    _seq: int = 0
    _stop: threading.Event = field(default_factory=threading.Event)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _subscribers: list[asyncio.Queue[dict]] = field(default_factory=list)
    _loop: asyncio.AbstractEventLoop | None = None

    @property
    def terminal(self) -> bool:
        return self.status in _TERMINAL


class RunManager:
    def __init__(self) -> None:
        self._runs: dict[str, Run] = {}

    def create(self, kind: str, params: dict) -> Run:
        created_at = datetime.now(UTC).isoformat(timespec="seconds")
        run = Run(id=uuid.uuid4().hex, kind=kind, params=params, created_at=created_at)
        self._runs[run.id] = run
        return run

    def get(self, run_id: str) -> Run | None:
        return self._runs.get(run_id)

    def list(self) -> list[Run]:
        """All runs, newest first (insertion order is launch order)."""
        return list(reversed(self._runs.values()))

    def clear(self, *, agent_id: str | None = None) -> int:
        """Drop finished runs (optionally only one agent's). Active runs
        (pending/running) are kept so a purge never abandons an in-flight
        execution. This is the ephemeral run read-model only -- it NEVER
        touches the append-only audit event store (I1). Returns the count
        removed."""
        removed = 0
        for run_id, run in list(self._runs.items()):
            if run.status in ("pending", "running"):
                continue
            if agent_id is not None and run.params.get("agent_id") != agent_id:
                continue
            del self._runs[run_id]
            removed += 1
        return removed

    def request_stop(self, run_id: str) -> bool:
        run = self._runs.get(run_id)
        if run is None:
            return False
        run._stop.set()
        return True

    async def subscribe(self, run: Run) -> asyncio.Queue[dict]:
        """Attach an asyncio queue, replaying buffered frames; registers the loop once."""
        queue: asyncio.Queue[dict] = asyncio.Queue()
        loop = asyncio.get_running_loop()
        with run._lock:
            if run._loop is None:
                run._loop = loop
            for frame in run.events:  # replay buffer for a late subscriber
                queue.put_nowait(frame)
            run._subscribers.append(queue)
        return queue

    def unsubscribe(self, run: Run, queue: asyncio.Queue[dict]) -> None:
        with run._lock:
            if queue in run._subscribers:
                run._subscribers.remove(queue)

    def _emit(self, run: Run, type_: str, data: dict) -> None:
        with run._lock:
            frame = {"seq": run._seq, "type": type_, "data": data}
            run._seq += 1
            run.events.append(frame)
            subs = list(run._subscribers)
            loop = run._loop
        for q in subs:
            if loop is not None:
                loop.call_soon_threadsafe(q.put_nowait, frame)

    def _execute(self, run: Run, runner: Runner) -> None:
        run.status = "running"
        self._emit(run, "start", {"kind": run.kind})
        try:
            runner(run.params, lambda t, d: self._emit(run, t, d), run._stop.is_set)
            run.status = "stopped" if run._stop.is_set() else "completed"
        except Exception as exc:  # broad: surface runner errors as a frame, not crash the thread
            run.status = "failed"
            run.error = str(exc)
            self._emit(run, "error", {"message": str(exc)})
        self._emit(run, "end", {"status": run.status})

    def start(self, run: Run, runner: Runner) -> threading.Thread:
        thread = threading.Thread(target=self._execute, args=(run, runner), daemon=True)
        thread.start()
        return thread

    def run_blocking(self, run: Run, runner: Runner) -> None:
        """Test/inline helper: execute in the calling thread (no background thread)."""
        self._execute(run, runner)
