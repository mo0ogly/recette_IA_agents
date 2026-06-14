"""real_saas proxy: bridges the I5 proxy protocol to a real forge.

The proxy ``router`` deliberately refuses ``real_saas`` (it is pure, reads no env,
holds no credentials). This module is the missing wiring: a ``RealForgeProxy`` adapts
a forge -- in practice the ``AllowlistForge`` over ``RealForge`` built by
``recette.realmode`` -- to ``ExternalSystemProxy.execute(event)``.

Safety (recette-corpus, R8):
- Lab stays the default everywhere; this proxy is opt-in.
- The forge is allowlisted (``AllowlistForge``) so a real run can only touch test
  orgs/resources, and writes are disabled unless explicitly enabled.
- Tokens come from the environment, held by the forge, never by decision code.

Failure mode (fail-safe, failure-modes.md): an allowlist rejection, a blocked write,
a missing SDK or any forge error is mapped to ``ExecutionResult(ok=False, ...)``. The
proxy never raises through the gateway and never bypasses; the gateway then appends an
auditable failure event.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..events import PlatformActionEvent
from .protocol import ExecutionResult, ExternalSystemProxy, side_effect_hash

# HTTP-ish status codes used to classify forge outcomes for the audit trail. The real
# forge speaks SDKs, not HTTP, so these are a stable internal classification, not a
# wire status: 200 success, 403 allowlist/write refusal, 502 forge/SDK error.
_STATUS_OK = 200
_STATUS_FORBIDDEN = 403
_STATUS_FORGE_ERROR = 502


@runtime_checkable
class _Forge(Protocol):
    """Minimal forge surface used by the adapter (matches GitForge.execute)."""

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
    ) -> object: ...


class RealForgeProxy:
    """ExternalSystemProxy backed by a (typically allowlisted) real forge.

    ``principal`` is taken from ``event.extra['principal']`` when present, else the
    bound ``event.agent_id`` (the identity the gateway resolved, I3). ``approved`` is
    derived from the event's approval state so a write that required approval only goes
    through once approved (I6).
    """

    def __init__(self, forge: _Forge) -> None:
        self._forge = forge

    def execute(self, event: PlatformActionEvent) -> ExecutionResult:
        principal = str(event.extra.get("principal") or event.agent_id)
        approved = event.approval_state == "approved"
        try:
            action = self._forge.execute(
                agent_id=event.agent_id,
                principal=principal,
                target_system=event.target_system,
                action_type=event.action_type,
                resource=event.resource,
                approved=approved,
                params=dict(event.payload),
            )
        except PermissionError as exc:
            # Write blocked (enable_writes=False) -- fail-safe, not a bypass.
            return ExecutionResult(
                ok=False, status_code=_STATUS_FORBIDDEN, error=f"real forge refused: {exc}"
            )
        except Exception as exc:  # noqa: BLE001 - allowlist/SDK/transport errors must not raise through
            # Covers RealModeError (allowlist), missing SDK, and live SDK failures.
            return ExecutionResult(
                ok=False, status_code=_STATUS_FORGE_ERROR, error=f"real forge error: {exc}"
            )
        response = action.to_dict() if hasattr(action, "to_dict") else {"action": str(action)}
        return ExecutionResult(
            ok=True,
            status_code=_STATUS_OK,
            response=response,
            side_effect_hash=side_effect_hash(
                event.target_system, event.action_type, event.resource, response
            ),
        )


def build_real_proxy_factory(*, enable_writes: bool = False):
    """Build a ``real_proxy_factory`` for ``resolve_proxy`` (impure: reads env).

    The returned closure takes a ``real_saas`` server entry and builds the
    ExternalSystemProxy for that server's system, dispatching by ``system``:
    ``slack`` -> ``RealSlackProxy`` (Slack Web API), any forge -> ``RealForgeProxy``
    over the allowlisted real forge (``recette.realmode``). Each proxy holds its
    own credentials from env (R8). ``enable_writes`` stays False by default so a
    real run cannot mutate an external system unless explicitly opted in.

    Imports stay lazy so the lab path keeps importing without either real-mode
    dependency chain.
    """

    def factory(server: dict) -> ExternalSystemProxy:
        system = server.get("system")
        if not isinstance(system, str) or not system:
            raise ValueError(
                f"real_saas server {server.get('id', '?')!r} requires a non-empty 'system'"
            )
        if system == "slack":
            from .real_slack_proxy import build_slack_proxy_from_env

            return build_slack_proxy_from_env(enable_writes=enable_writes)
        from ...realmode import build_real_forge

        forge = build_real_forge(system, enable_writes=enable_writes)
        return RealForgeProxy(forge)

    return factory
