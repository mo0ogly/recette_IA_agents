"""Wire routing plumbing: the optional proxy_url seam through the client.

Deterministic and offline: asserts the explicit-proxy opener is built only when
a proxy_url is given, and that resolve_proxy threads wire_proxy_url into the
lab-mode proxies without touching the direct (None) default path (I4).
"""

from __future__ import annotations

import unittest

from recette._http_client import StdlibHttpClient
from recette.platform.proxy.lab_proxy import LabHttpProxy
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


if __name__ == "__main__":
    unittest.main()
