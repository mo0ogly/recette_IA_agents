"""ExternalSystemProxy protocol (I5).

Business/decision code never calls an external system directly: every side
effect goes through a proxy that produces a side_effect_hash recorded in the
audit event. Proxies are the only components that would hold credentials in
real mode (R8); the lab proxy holds none.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from ..events import PlatformActionEvent


def side_effect_hash(target_system: str, action_type: str, resource: str, response: dict) -> str:
    """Deterministic hash of the produced side effect (audit/replay, I1/I4)."""
    blob = json.dumps(
        {
            "target_system": target_system,
            "action_type": action_type,
            "resource": resource,
            "response": response,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ExecutionResult:
    ok: bool
    status_code: int
    response: dict = field(default_factory=dict)
    side_effect_hash: str | None = None
    error: str | None = None
    # The resolved server name (fqdn) the side effect was routed to, for trace
    # realism (a trace reads ``api.github.com`` instead of ``127.0.0.1:9101``).
    # None means no name was resolved -> the trace falls back to target_system,
    # exactly the previous behaviour (back-compat).
    target: str | None = None

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "status_code": self.status_code,
            "response": self.response,
            "side_effect_hash": self.side_effect_hash,
            "error": self.error,
            "target": self.target,
        }


@runtime_checkable
class ExternalSystemProxy(Protocol):
    def execute(self, event: PlatformActionEvent) -> ExecutionResult:
        """Execute the side effect. Failure returns ok=False -- never raises
        through the gateway and never bypasses (failure-modes.md)."""
        ...
