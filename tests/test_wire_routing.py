"""Wire routing plumbing: the optional proxy_url seam through the client.

Deterministic and offline: asserts the explicit-proxy opener is built only when
a proxy_url is given, and that resolve_proxy threads wire_proxy_url into the
lab-mode proxies without touching the direct (None) default path (I4).
"""

from __future__ import annotations

import os
import ssl
import unittest

from recette._http_client import StdlibHttpClient
from recette.platform.proxy.lab_proxy import LabHttpProxy
from recette.platform.proxy.real_slack_proxy import RealSlackProxy, build_slack_proxy_from_env
from recette.platform.proxy.router import resolve_proxy

WIRE = "http://127.0.0.1:8083"


class StdlibClientProxyTests(unittest.TestCase):
    def test_no_proxy_means_no_custom_opener(self) -> None:
        client = StdlibHttpClient("http://localhost:8082")
        self.assertIsNone(client.proxy_url)
        self.assertIsNone(client._opener)

    def test_proxy_builds_a_custom_opener(self) -> None:
        client = StdlibHttpClient("http://localhost:8082", proxy_url=WIRE)
        self.assertEqual(client.proxy_url, WIRE)
        self.assertIsNotNone(client._opener)

    def test_empty_proxy_url_is_treated_as_direct(self) -> None:
        # An empty string is falsy -> no opener (no accidental proxy to "").
        client = StdlibHttpClient("http://localhost:8082", proxy_url="")
        self.assertIsNone(client._opener)

    def test_ca_bundle_builds_a_custom_opener(self) -> None:
        # A real PEM (the system trust store) so create_default_context succeeds.
        ca = ssl.get_default_verify_paths().cafile
        if ca is None:
            self.skipTest("no system CA file to point at")
        client = StdlibHttpClient("https://api.example", ca_bundle=ca)
        self.assertEqual(client.ca_bundle, ca)
        self.assertIsNotNone(client._opener)

    def test_proxy_and_ca_combine(self) -> None:
        ca = ssl.get_default_verify_paths().cafile
        if ca is None:
            self.skipTest("no system CA file to point at")
        client = StdlibHttpClient("https://api.example", proxy_url=WIRE, ca_bundle=ca)
        self.assertEqual((client.proxy_url, client.ca_bundle), (WIRE, ca))
        self.assertIsNotNone(client._opener)

    def test_neither_proxy_nor_ca_is_direct(self) -> None:
        client = StdlibHttpClient("https://api.example")
        self.assertIsNone(client._opener)


class ResolveProxyWireTests(unittest.TestCase):
    SERVERS = [
        {"id": "lab-gh", "mode": "mock_local", "port": 9101},
        {"id": "decl", "mode": "declared_url", "base_url": "http://example.test"},
    ]

    def _default(self) -> LabHttpProxy:
        return LabHttpProxy("http://localhost:8082")

    def test_mock_local_threads_wire_proxy(self) -> None:
        proxy = resolve_proxy(
            {"server": "lab-gh"}, self.SERVERS, self._default(), wire_proxy_url=WIRE
        )
        assert isinstance(proxy, LabHttpProxy)
        self.assertEqual(proxy._client.proxy_url, WIRE)

    def test_declared_url_threads_wire_proxy(self) -> None:
        proxy = resolve_proxy(
            {"server": "decl"}, self.SERVERS, self._default(), wire_proxy_url=WIRE
        )
        assert isinstance(proxy, LabHttpProxy)
        self.assertEqual(proxy._client.proxy_url, WIRE)

    def test_without_wire_proxy_the_lab_path_is_direct(self) -> None:
        proxy = resolve_proxy({"server": "lab-gh"}, self.SERVERS, self._default())
        assert isinstance(proxy, LabHttpProxy)
        self.assertIsNone(proxy._client.proxy_url)

    def test_no_server_returns_default_untouched(self) -> None:
        default = self._default()
        proxy = resolve_proxy({}, self.SERVERS, default, wire_proxy_url=WIRE)
        self.assertIs(proxy, default)


def _system_ca() -> str:
    """A real CA PEM path; SkipTest if the platform has none (create_default_context
    validates the file eagerly, so the path must exist)."""
    ca = ssl.get_default_verify_paths().cafile
    if ca is None:
        raise unittest.SkipTest("no system CA file to point at")
    return ca


class RealSlackWireTests(unittest.TestCase):
    def test_constructor_threads_proxy_and_ca(self) -> None:
        ca = _system_ca()
        proxy = RealSlackProxy(token="x", allowlist=frozenset({"C1"}), proxy_url=WIRE, ca_bundle=ca)
        self.assertEqual(proxy._client.proxy_url, WIRE)
        self.assertEqual(proxy._client.ca_bundle, ca)

    def test_without_wire_the_slack_client_is_direct(self) -> None:
        proxy = RealSlackProxy(token="x", allowlist=frozenset({"C1"}))
        self.assertIsNone(proxy._client.proxy_url)
        self.assertIsNone(proxy._client.ca_bundle)

    def test_env_builder_reads_wire_env(self) -> None:
        ca = _system_ca()
        env = {
            "SLACK_BOT_TOKEN": "xoxb-test",
            "INSPECT_IA_AGENTS_SLACK_CHANNEL_ALLOWLIST": "C1,C2",
            "INSPECT_IA_AGENTS_WIRE_PROXY": WIRE,
            "INSPECT_IA_AGENTS_WIRE_CA": ca,
        }
        saved = {k: os.environ.get(k) for k in env}
        os.environ.update(env)
        try:
            proxy = build_slack_proxy_from_env()
            self.assertEqual(proxy._client.proxy_url, WIRE)
            self.assertEqual(proxy._client.ca_bundle, ca)
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


if __name__ == "__main__":
    unittest.main()
