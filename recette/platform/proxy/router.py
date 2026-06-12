"""Per-agent proxy routing via the server registry (I5).

An agent entry may carry a ``server`` field naming one entry of the config
server registry (``{"id", "system", "mode", ...}``). resolve_proxy() picks
the ExternalSystemProxy a run must execute through:

- no ``server`` field (or empty) -> the provided default proxy;
- ``mock_local``   -> LabHttpProxy("http://localhost:{port}");
- ``declared_url`` -> LabHttpProxy(base_url). The lab wire format
  (``POST /{target_system}/execute`` returning the ``{"success", "data"}``
  envelope) is the contract: a declared server MUST speak it;
- ``real_saas``    -> ValueError. recette/realmode.py only exposes
  forge-level wrappers (AllowlistForge over GitForge), not an
  ExternalSystemProxy implementation, so there is no real-SaaS proxy to
  route to yet. Fail-safe: never fall back to the default.

Failure modes (fail-safe, this module never falls back silently):
- the agent references a server id absent from the registry -> ValueError.
  A dangling reference must fail the run; the default proxy is NEVER
  silently substituted (that would execute side effects against the wrong
  system, violating I5).
- unsupported/unknown server mode, or a malformed required field
  (non-integer ``port``, empty ``base_url``) -> ValueError.

Purity: this function does no I/O and reads no environment. Constructing a
LabHttpProxy is allowed because it performs no I/O at construction time.
"""

from __future__ import annotations

from .lab_proxy import LabHttpProxy
from .protocol import ExternalSystemProxy


def resolve_proxy(
    agent: dict, servers: list[dict], default: ExternalSystemProxy
) -> ExternalSystemProxy:
    """Resolve the proxy for one agent run from the server registry.

    Raises ValueError on a dangling server reference, an unsupported mode,
    or a malformed server entry (fail-safe: the run must fail, never
    execute through the wrong proxy).
    """
    server_id = agent.get("server")
    if not server_id:
        return default
    server = next((s for s in servers if s.get("id") == server_id), None)
    if server is None:
        raise ValueError(f"agent {agent.get('id', '?')!r} references unknown server {server_id!r}")
    mode = server.get("mode")
    if mode == "mock_local":
        port = server.get("port")
        if not isinstance(port, int) or isinstance(port, bool):
            raise ValueError(f"server {server_id!r} (mock_local) requires an integer 'port'")
        return LabHttpProxy(f"http://localhost:{port}")
    if mode == "declared_url":
        base_url = server.get("base_url")
        if not isinstance(base_url, str) or not base_url:
            raise ValueError(f"server {server_id!r} (declared_url) requires a non-empty 'base_url'")
        # The declared server must implement the lab wire format (module docstring).
        return LabHttpProxy(base_url)
    if mode == "real_saas":
        raise ValueError("real_saas execution requires realmode wiring")
    raise ValueError(f"server {server_id!r} has unsupported mode {mode!r}")
