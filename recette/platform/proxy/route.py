"""Runtime-selectable proxy route for agent side effects (transport, not decision).

The agent's side effects (I5) always go through the gateway/proxy; this registry
only chooses the **transport** they take to reach the target: directly, or through
the optional mitmproxy wire overlay so the bytes are captured. It is observability
plumbing -- changing the route never changes the decision (allow/deny/escalate) or
the recorded action log, so it does not touch determinism (I4): a replay rebuilds
the same decision regardless of which transport carried the live side effect.

The active selection is a runtime, in-memory choice (app.state), surfaced in the
network-debug consoles so an operator can flip routing without restarting. The
deterministic recette never uses this registry: it builds runners directly with a
direct transport.
"""

from __future__ import annotations

import threading
from dataclasses import asdict, dataclass

# Canonical default for the wire overlay (mirrors cicd WIRE_PORT). Used when the
# wire target is offered without an explicit INSPECT_IA_AGENTS_WIRE_PROXY override.
DEFAULT_WIRE_URL = "http://127.0.0.1:8083"

DIRECT_ID = "direct"
WIRE_ID = "wire"


@dataclass(frozen=True)
class ProxyTarget:
    """One selectable transport. ``proxy_url`` is None for the direct route."""

    id: str
    label: str
    proxy_url: str | None

    def to_dict(self) -> dict:
        return asdict(self)


class ProxyRouteRegistry:
    """Thread-safe registry of transport targets + the active selection.

    Always offers ``direct`` (no proxy) and ``wire`` (the mitmproxy overlay). The
    wire URL comes from configuration (R5: INSPECT_IA_AGENTS_WIRE_PROXY) or the
    canonical default. The initial active route is ``wire`` when the env named a
    proxy (the operator opted in), else ``direct`` -- so behaviour matches the
    pre-selector world until someone flips it.
    """

    def __init__(self, *, wire_url: str | None = None, active_from_env: bool = False) -> None:
        resolved_wire = wire_url or DEFAULT_WIRE_URL
        self._targets: dict[str, ProxyTarget] = {
            DIRECT_ID: ProxyTarget(DIRECT_ID, "Direct (sans proxy)", None),
            WIRE_ID: ProxyTarget(WIRE_ID, "Wire (mitmproxy)", resolved_wire),
        }
        self._active = WIRE_ID if active_from_env else DIRECT_ID
        self._lock = threading.Lock()

    def targets(self) -> list[ProxyTarget]:
        with self._lock:
            return list(self._targets.values())

    def active(self) -> str:
        with self._lock:
            return self._active

    def active_proxy_url(self) -> str | None:
        with self._lock:
            return self._targets[self._active].proxy_url

    def set_active(self, target_id: str) -> ProxyTarget:
        """Select the active transport. Raises ValueError on an unknown id
        (fail-safe: never silently keep the old route on a bad selection)."""
        with self._lock:
            if target_id not in self._targets:
                known = ", ".join(self._targets)
                raise ValueError(f"unknown proxy target {target_id!r}; known: {known}")
            self._active = target_id
            return self._targets[target_id]


def registry_from_env() -> ProxyRouteRegistry:
    """Build the registry from the environment (R5). The wire target URL is the
    INSPECT_IA_AGENTS_WIRE_PROXY value when set; the active route starts on ``wire``
    only if that env named a proxy (operator opt-in), else ``direct``."""
    from .wire import wire_proxy_url_from_env

    wire = wire_proxy_url_from_env()
    return ProxyRouteRegistry(wire_url=wire, active_from_env=wire is not None)
