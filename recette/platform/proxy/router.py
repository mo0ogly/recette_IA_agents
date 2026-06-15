"""Per-agent proxy routing via the server registry (I5).

An agent entry may carry a ``server`` field naming one entry of the config
server registry (``{"id", "system", "mode", ...}``). resolve_proxy() picks
the ExternalSystemProxy a run must execute through:

- no ``server`` field (or empty) -> the provided default proxy;
- ``mock_local``   -> LabHttpProxy("http://127.0.0.1:{port}"). The literal
  loopback IP matches ServerManager, which binds and health-checks 127.0.0.1;
  "localhost" may resolve to ::1 first and miss the bound IPv4 socket;
- ``declared_url`` -> LabHttpProxy(base_url). The lab wire format
  (``POST /{target_system}/execute`` returning the ``{"success", "data"}``
  envelope) is the contract: a declared server MUST speak it;
- ``real_saas``    -> the injected ``real_proxy_factory(server)`` when one is
  provided (the call-site -- runners/api -- builds a RealForgeProxy over an
  allowlisted real forge, holding the env token). When NO factory is injected,
  ValueError: this module is pure and holds no credentials, so it cannot build a
  real proxy itself. Fail-safe either way: never fall back to the default.

Failure modes (fail-safe, this module never falls back silently):
- the agent references a server id absent from the registry -> ValueError.
  A dangling reference must fail the run; the default proxy is NEVER
  silently substituted (that would execute side effects against the wrong
  system, violating I5).
- unsupported/unknown server mode, or a malformed required field
  (non-integer ``port``, empty ``base_url``) -> ValueError.

Purity: this function does no I/O and reads no environment. Constructing a
LabHttpProxy is allowed because it performs no I/O at construction time. The
``real_proxy_factory`` is the single seam through which a real-mode proxy (which
DOES touch env/credentials) is injected from an impure call-site, keeping this
router pure and deterministic.
"""

from __future__ import annotations

from collections.abc import Callable

from ..netname.resolver import resolve_name
from .lab_proxy import LabHttpProxy
from .protocol import ExternalSystemProxy

RealProxyFactory = Callable[[dict], ExternalSystemProxy]


def resolve_proxy(
    agent: dict,
    servers: list[dict],
    default: ExternalSystemProxy,
    *,
    real_proxy_factory: RealProxyFactory | None = None,
    wire_proxy_url: str | None = None,
) -> ExternalSystemProxy:
    """Resolve the proxy for one agent run from the server registry.

    ``real_proxy_factory`` (optional) builds the ExternalSystemProxy for a
    ``real_saas`` server entry; it is invoked with that server dict. When omitted,
    a ``real_saas`` entry raises ValueError (this module holds no credentials).

    ``wire_proxy_url`` (optional) routes the lab-mode proxies (mock_local,
    declared_url) through the mitmproxy wire overlay. It is INJECTED by the
    impure call-site (which reads the env), keeping this module pure: None ->
    direct, exactly the previous behaviour (I4). real_saas is unaffected (its
    proxy is built by the factory; real targets are HTTPS and would need the
    overlay CA, out of the phase-1 lab scope).

    Raises ValueError on a dangling server reference, an unsupported mode,
    or a malformed server entry (fail-safe: the run must fail, never
    execute through the wrong proxy).
    """
    server_ref = agent.get("server")
    if not server_ref:
        return default
    # Realism resolution (Task 5): resolve the reference by name (fqdn/alias/id)
    # with containment OFF -- resolve_name's third pass already matches by id, so
    # an unknown name returns None and the reference is dangling (no separate id
    # lookup needed). A dangling reference fails the run (fail-safe). The deny path
    # (containment ON) is Task 6 and is intentionally NOT wired here. resolve_name
    # is pure (no I/O), so the router stays pure (I4).
    server = resolve_name(server_ref, servers, containment=False)
    if server is None:
        raise ValueError(f"agent {agent.get('id', '?')!r} references unknown server {server_ref!r}")
    server_id = server.get("id", server_ref)
    # The resolved server name (fqdn, if any) becomes the trace target for the
    # lab-mode proxies, so a trace reads the fqdn instead of the loopback IP.
    fqdn = server.get("fqdn")
    target_name = fqdn if isinstance(fqdn, str) and fqdn else None
    mode = server.get("mode")
    if mode == "mock_local":
        port = server.get("port")
        if not isinstance(port, int) or isinstance(port, bool):
            raise ValueError(f"server {server_id!r} (mock_local) requires an integer 'port'")
        return LabHttpProxy(
            f"http://127.0.0.1:{port}", proxy_url=wire_proxy_url, target_name=target_name
        )
    if mode == "declared_url":
        base_url = server.get("base_url")
        if not isinstance(base_url, str) or not base_url:
            raise ValueError(f"server {server_id!r} (declared_url) requires a non-empty 'base_url'")
        # The declared server must implement the lab wire format (module docstring).
        return LabHttpProxy(base_url, proxy_url=wire_proxy_url, target_name=target_name)
    if mode == "real_saas":
        if real_proxy_factory is None:
            raise ValueError("real_saas execution requires realmode wiring")
        return real_proxy_factory(server)
    raise ValueError(f"server {server_id!r} has unsupported mode {mode!r}")
