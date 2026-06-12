# tests/test_proxy_router.py
"""B6: per-agent proxy routing via the server registry (I5).

resolve_proxy is pure: given the agent entry, the configured servers and the
default proxy, it returns the ExternalSystemProxy the run must execute
through, or raises ValueError (fail-safe: a dangling/unsupported server
reference must fail the run, never silently fall back to the default).
"""

from __future__ import annotations

import unittest

from recette.platform.proxy.lab_proxy import LabHttpProxy
from recette.platform.proxy.router import resolve_proxy

SERVERS = [
    {"id": "gh-mock", "system": "github", "mode": "mock_local", "port": 9101},
    {
        "id": "gl-lab",
        "system": "gitlab",
        "mode": "declared_url",
        "base_url": "http://lab.internal:9000",
    },
    {"id": "okta-prod", "system": "okta", "mode": "real_saas", "owner": "secops"},
]


def _base_url(proxy: LabHttpProxy) -> str:
    # StdlibHttpClient exposes a public base_url; the client handle on the
    # proxy is private, which is acceptable introspection in tests.
    return proxy._client.base_url  # noqa: SLF001


class ProxyRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.default = LabHttpProxy("http://localhost:8082")

    def test_agent_without_server_returns_the_exact_default(self) -> None:
        agent = {"id": "a1", "target_system": "github"}
        resolved = resolve_proxy(agent, SERVERS, self.default)
        self.assertIs(resolved, self.default)

    def test_agent_with_empty_server_returns_the_exact_default(self) -> None:
        agent = {"id": "a1", "target_system": "github", "server": ""}
        resolved = resolve_proxy(agent, SERVERS, self.default)
        self.assertIs(resolved, self.default)

    def test_mock_local_routes_to_localhost_port(self) -> None:
        agent = {"id": "a1", "target_system": "github", "server": "gh-mock"}
        resolved = resolve_proxy(agent, SERVERS, self.default)
        self.assertIsInstance(resolved, LabHttpProxy)
        self.assertIsNot(resolved, self.default)
        self.assertEqual(_base_url(resolved), "http://localhost:9101")

    def test_declared_url_routes_to_base_url(self) -> None:
        agent = {"id": "a2", "target_system": "gitlab", "server": "gl-lab"}
        resolved = resolve_proxy(agent, SERVERS, self.default)
        self.assertIsInstance(resolved, LabHttpProxy)
        self.assertEqual(_base_url(resolved), "http://lab.internal:9000")

    def test_unknown_server_id_is_an_error_not_a_fallback(self) -> None:
        agent = {"id": "a1", "target_system": "github", "server": "gh-missing"}
        with self.assertRaises(ValueError) as ctx:
            resolve_proxy(agent, SERVERS, self.default)
        self.assertIn("gh-missing", str(ctx.exception))

    def test_real_saas_requires_realmode_wiring(self) -> None:
        # recette/realmode.py exposes forge-level wrappers (AllowlistForge),
        # not an ExternalSystemProxy implementation -> fail-safe error.
        agent = {"id": "a3", "target_system": "okta", "server": "okta-prod"}
        with self.assertRaises(ValueError) as ctx:
            resolve_proxy(agent, SERVERS, self.default)
        self.assertIn("real_saas execution requires realmode wiring", str(ctx.exception))

    def test_unsupported_mode_is_an_error(self) -> None:
        servers = [{"id": "weird", "system": "github", "mode": "carrier_pigeon"}]
        agent = {"id": "a1", "target_system": "github", "server": "weird"}
        with self.assertRaises(ValueError) as ctx:
            resolve_proxy(agent, servers, self.default)
        self.assertIn("weird", str(ctx.exception))

    def test_mock_local_without_integer_port_is_an_error(self) -> None:
        servers = [{"id": "gh-bad", "system": "github", "mode": "mock_local", "port": "9101"}]
        agent = {"id": "a1", "target_system": "github", "server": "gh-bad"}
        with self.assertRaises(ValueError) as ctx:
            resolve_proxy(agent, servers, self.default)
        self.assertIn("gh-bad", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
