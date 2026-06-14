"""LB6 -- real-mode guard for Lane B agents.

Real mode is opt-in and dangerous: it acts on real systems with real tokens. This module
makes it SAFE by construction:

- AllowlistForge wraps any forge and refuses to execute against a resource that is not in
  an explicit allowlist of test orgs/endpoints (so a real run can never touch a repo it was
  not authorised for).
- build_real_forge reads the token from the environment (R8, never hardcoded) and keeps
  writes disabled unless explicitly enabled.

Lab stays the default everywhere; CI only ever runs lab.
"""

from __future__ import annotations

import os
from fnmatch import fnmatch

from .events import AgentAction
from .forge import GitForge, RealForge

ALLOWLIST_ENV = "INSPECT_IA_AGENTS_REAL_ALLOWLIST"


class RealModeError(RuntimeError):
    """Raised when real mode is misconfigured or a resource is outside the allowlist."""


def parse_allowlist(raw: str | None) -> list[str]:
    """Comma-separated allowlist of resource glob patterns (e.g. 'acme-test/*,demo/*')."""
    if not raw:
        return []
    return [p.strip() for p in raw.split(",") if p.strip()]


def is_allowed(resource: str, allowlist: list[str]) -> bool:
    return any(fnmatch(resource, pattern) for pattern in allowlist)


class AllowlistForge:
    """Wraps a forge; only lets actions through whose resource matches the allowlist."""

    def __init__(self, inner: GitForge, allowlist: list[str]) -> None:
        if not allowlist:
            raise RealModeError(f"real mode requires a non-empty allowlist (set {ALLOWLIST_ENV})")
        self._inner = inner
        self._allowlist = allowlist

    def execute(
        self,
        *,
        agent_id: str,
        principal: str,
        target_system: str,
        action_type: str,
        resource: str,
        approved: bool = False,
        params: dict | None = None,
    ) -> AgentAction:
        if not is_allowed(resource, self._allowlist):
            raise RealModeError(
                f"resource {resource!r} is not in the real-mode allowlist {self._allowlist}"
            )
        return self._inner.execute(
            agent_id=agent_id,
            principal=principal,
            target_system=target_system,
            action_type=action_type,
            resource=resource,
            approved=approved,
            params=params,
        )

    @property
    def action_log(self) -> list[AgentAction]:
        return self._inner.action_log


def build_real_forge(target_system: str, *, enable_writes: bool = False) -> AllowlistForge:
    """Build an allowlisted RealForge from the environment. Token + allowlist via env (R8)."""
    token_var = f"INSPECT_IA_AGENTS_{target_system.upper()}_TOKEN"
    token = os.environ.get(token_var)
    if not token:
        raise RealModeError(f"real mode needs {token_var} in the environment")
    # Fail fast on config (don't even connect the SDK) before building the real forge.
    allowlist = parse_allowlist(os.environ.get(ALLOWLIST_ENV))
    if not allowlist:
        raise RealModeError(f"real mode requires a non-empty allowlist (set {ALLOWLIST_ENV})")
    inner = RealForge(target_system, token=token, enable_writes=enable_writes)
    return AllowlistForge(inner, allowlist)
