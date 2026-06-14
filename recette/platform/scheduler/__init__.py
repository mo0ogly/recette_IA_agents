"""Autonomous maintenance scheduler (G8) -- closes the G2 sweep + G4 flush residuals.

``build_scheduler_from_env`` selects the heartbeat by ``INSPECT_IA_AGENTS_SCHEDULER``:

    off (default) -> NullScheduler (no background timer; deterministic tests/replay)
    inproc        -> InProcessScheduler (real asyncio heartbeat, mono-host Phase 1)

Interval via ``INSPECT_IA_AGENTS_SCHEDULER_INTERVAL_SECONDS`` (default 30, floor 1). The
scheduler is built with its tasks already bound, so env selection stays free of any
gateway/transport wiring.
"""

from __future__ import annotations

import os
from collections.abc import Sequence

from .inproc import (
    DEFAULT_INTERVAL_SECONDS,
    MIN_INTERVAL_SECONDS,
    InProcessScheduler,
    NullScheduler,
)
from .protocol import ScheduledTask, Scheduler, TaskFn

__all__ = [
    "DEFAULT_INTERVAL_SECONDS",
    "MIN_INTERVAL_SECONDS",
    "InProcessScheduler",
    "NullScheduler",
    "ScheduledTask",
    "Scheduler",
    "SchedulerConfigError",
    "TaskFn",
    "build_scheduler_from_env",
]


class SchedulerConfigError(RuntimeError):
    """Raised when ``INSPECT_IA_AGENTS_SCHEDULER*`` env is malformed (fail-safe)."""


def build_scheduler_from_env(tasks: Sequence[ScheduledTask]) -> Scheduler:
    """Construct the scheduler selected by ``INSPECT_IA_AGENTS_SCHEDULER`` (default off)."""
    backend = os.environ.get("INSPECT_IA_AGENTS_SCHEDULER", "off").strip().lower()
    if backend in ("off", ""):
        return NullScheduler()
    if backend == "inproc":
        return InProcessScheduler(tasks, interval_seconds=_interval_from_env())
    raise SchedulerConfigError(
        f"unknown INSPECT_IA_AGENTS_SCHEDULER={backend!r} (expected 'off' or 'inproc')"
    )


def _interval_from_env() -> float:
    raw = os.environ.get("INSPECT_IA_AGENTS_SCHEDULER_INTERVAL_SECONDS")
    if raw is None or not raw.strip():
        return DEFAULT_INTERVAL_SECONDS
    try:
        interval = float(raw)
    except ValueError as exc:
        raise SchedulerConfigError(
            f"INSPECT_IA_AGENTS_SCHEDULER_INTERVAL_SECONDS must be a number, got {raw!r}"
        ) from exc
    if interval < MIN_INTERVAL_SECONDS:
        raise SchedulerConfigError(
            f"INSPECT_IA_AGENTS_SCHEDULER_INTERVAL_SECONDS must be >= {MIN_INTERVAL_SECONDS}"
        )
    return interval
