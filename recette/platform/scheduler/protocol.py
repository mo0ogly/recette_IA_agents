"""Scheduler protocol -- the ops heartbeat that fires periodic platform maintenance.

The scheduler lives OUTSIDE the decision path (I4): it never calls ``decide()``. It
periodically runs registered maintenance tasks (approval timeout sweep, realtime buffer
flush) whose effects are already invariant-safe -- the sweep only appends TIMEOUT events
(never auto-approves, I6) and takes its clock as a captured input, the flush only drains
an already-persisted derived copy (I1). The wall clock read at a tick boundary is
operational metadata, not a decision input.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

# A task receives ``now_iso`` captured once at the tick boundary and returns an outcome
# count (events swept / still-pending) used only for structured logging.
TaskFn = Callable[[str], int]


@dataclass(frozen=True)
class ScheduledTask:
    """A named maintenance task driven by the heartbeat."""

    name: str
    run: TaskFn


@runtime_checkable
class Scheduler(Protocol):
    """Start/stop a background heartbeat; ``run_once`` is the synchronous tick."""

    def start(self) -> None: ...

    async def stop(self) -> None: ...

    def run_once(self, now_iso: str | None = None) -> dict[str, int]: ...
