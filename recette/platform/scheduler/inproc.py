"""InProcessScheduler -- a real asyncio heartbeat for Phase-1 mono-host deployments.

Default-off (``INSPECT_IA_AGENTS_SCHEDULER``): a self-firing clock that mutates state (appends
TIMEOUT events) must be enabled deliberately per deployment so tests and replay stay
deterministic (I4). Production sets ``INSPECT_IA_AGENTS_SCHEDULER=inproc``.

Fail-safe (failure-modes.md): a failing task is isolated -- logged, never killing the
loop or the app. The tick logic (``run_once``) is synchronous and clock-injectable so it
is testable deterministically without a real timer; the asyncio loop is a thin wrapper.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import logging
from collections.abc import Callable, Sequence

from ..observability import log_correlated
from .protocol import ScheduledTask

_log = logging.getLogger("inspect_ia_agents.scheduler")

DEFAULT_INTERVAL_SECONDS = 30.0
MIN_INTERVAL_SECONDS = 1.0


def _wall_clock_iso() -> str:
    """Operational wall clock captured at a tick boundary (not a decision input)."""
    return _dt.datetime.now(_dt.UTC).isoformat().replace("+00:00", "Z")


class InProcessScheduler:
    """Run registered maintenance tasks on a fixed-interval asyncio heartbeat."""

    def __init__(
        self,
        tasks: Sequence[ScheduledTask],
        *,
        interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
        clock: Callable[[], str] = _wall_clock_iso,
    ) -> None:
        if interval_seconds < MIN_INTERVAL_SECONDS:
            raise ValueError(f"interval_seconds must be >= {MIN_INTERVAL_SECONDS}")
        self._tasks = tuple(tasks)
        self._interval = interval_seconds
        self._clock = clock
        self._task: asyncio.Task[None] | None = None

    def run_once(self, now_iso: str | None = None) -> dict[str, int]:
        """Fire every task once with a single captured clock; isolate failures."""
        now = now_iso if now_iso is not None else self._clock()
        outcomes: dict[str, int] = {}
        for task in self._tasks:
            try:
                outcome = task.run(now)
            except Exception as exc:  # noqa: BLE001 - a task failure must not kill the heartbeat
                _log.warning("scheduled task %r failed: %s", task.name, exc)
                outcomes[task.name] = -1
                continue
            outcomes[task.name] = outcome
            if outcome:
                log_correlated(
                    _log,
                    logging.INFO,
                    "scheduled task fired",
                    event_id=f"scheduler:{task.name}:{now}",
                    agent_id="system:scheduler",
                    kind=task.name,
                )
        return outcomes

    def start(self) -> None:
        """Schedule the heartbeat on the running event loop (idempotent)."""
        if self._task is not None:
            return
        self._task = asyncio.get_running_loop().create_task(self._loop())

    async def stop(self) -> None:
        """Cancel the heartbeat and await its termination."""
        task = self._task
        if task is None:
            return
        self._task = None
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            try:
                # Offload sync task I/O (SQLite sweep) off the event loop thread.
                await asyncio.to_thread(self.run_once)
            except Exception as exc:  # noqa: BLE001 - belt-and-braces: the loop survives anything
                _log.warning("scheduler tick failed: %s", exc)


class NullScheduler:
    """No-op scheduler (``INSPECT_IA_AGENTS_SCHEDULER=off``): the heartbeat is disabled."""

    def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    def run_once(self, now_iso: str | None = None) -> dict[str, int]:
        return {}
