"""Gateway middleware pipeline -- cross-cutting hooks around mediation (I2).

A reference pattern (agent-framework ``_middleware.py``) adapted to AgentRail's
control-plane discipline: a middleware may OBSERVE every submission and may force
a DENY, but it can NEVER grant -- only the Policy Engine produces an allow (I2).
A middleware raising in its ``before`` hook denies the action (fail-safe, never
fail-open); an exception in ``after`` is swallowed so observation can never change
an outcome. Middlewares must be deterministic (no clock/random) to preserve
replay (I4).

The pipeline is optional: a Gateway built without one behaves exactly as before.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from .gateway import ActionOutcome, ActionRequest


@runtime_checkable
class Middleware(Protocol):
    def before(self, request: ActionRequest) -> str | None:
        """Return a deny reason to short-circuit (deny), or None to continue."""
        ...

    def after(self, request: ActionRequest, outcome: ActionOutcome) -> None:
        """Observe the produced outcome. Must not raise meaningfully (swallowed)."""
        ...


class MiddlewarePipeline:
    """Runs middlewares in order: the first deny short-circuits; after-hooks observe."""

    def __init__(self, middlewares: list[Middleware] | None = None) -> None:
        self._middlewares = list(middlewares or [])

    def run_before(self, request: ActionRequest) -> str | None:
        for m in self._middlewares:
            try:
                reason = m.before(request)
            except Exception as exc:  # fail-safe: a broken guard denies, never allows
                return f"middleware {type(m).__name__} raised -> deny: {exc}"
            if reason is not None:
                return reason
        return None

    def run_after(self, request: ActionRequest, outcome: ActionOutcome) -> None:
        for m in self._middlewares:
            try:
                m.after(request, outcome)
            except Exception:  # observation must never alter the outcome
                continue


class RecordingMiddleware:
    """Observability middleware: records every submission and its verdict."""

    def __init__(self) -> None:
        self.before_seen: list[tuple[str, str, str]] = []
        self.after_seen: list[tuple[str, str]] = []

    def before(self, request: ActionRequest) -> str | None:
        self.before_seen.append((request.agent_id, request.target_system, request.action_type))
        return None

    def after(self, request: ActionRequest, outcome: ActionOutcome) -> None:
        self.after_seen.append((request.action_type, str(outcome.verdict)))


class DenyListMiddleware:
    """Fail-safe guard: deny any submission whose target_system is on the list."""

    def __init__(self, denied_targets: list[str]) -> None:
        self._denied = set(denied_targets)

    def before(self, request: ActionRequest) -> str | None:
        if request.target_system in self._denied:
            return f"target {request.target_system!r} denied by middleware guard"
        return None

    def after(self, request: ActionRequest, outcome: ActionOutcome) -> None:
        return None
