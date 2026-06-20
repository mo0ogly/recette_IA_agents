"""Wire run correlation: the lab proxy threads the originating run_id into the
outbound HTTP request as the ``x-inspect-run-id`` header so the mitmproxy wire
overlay can correlate raw network bytes back to a run/agent/session.

Transport metadata only: the header is set at client construction, never enters
the decision path (I4), and is harmless when wire is off (the lab ignores an
unknown header). This tests the proxy layer directly (no fastapi).
"""

from __future__ import annotations

import unittest

from recette.platform.proxy.lab_proxy import WIRE_RUN_HEADER, LabHttpProxy
from recette.platform.proxy.router import resolve_proxy


class WireRunCorrelationTest(unittest.TestCase):
    def test_lab_proxy_sets_run_header_when_run_id_given(self) -> None:
        proxy = LabHttpProxy("http://127.0.0.1:9999", run_id="RUN-123")
        self.assertEqual(proxy._client.headers.get(WIRE_RUN_HEADER), "RUN-123")

    def test_no_run_header_when_run_id_absent(self) -> None:
        proxy = LabHttpProxy("http://127.0.0.1:9999")
        self.assertNotIn(WIRE_RUN_HEADER, proxy._client.headers)


class ResolveProxyRunCorrelationTest(unittest.TestCase):
    SERVERS: list[dict] = [
        {"id": "lab-gh", "mode": "mock_local", "port": 9101},
        {"id": "decl", "mode": "declared_url", "base_url": "http://example.test"},
    ]

    def _default(self) -> LabHttpProxy:
        return LabHttpProxy("http://localhost:8082")

    def test_mock_local_threads_run_id(self) -> None:
        proxy = resolve_proxy(
            {"server": "lab-gh"},
            self.SERVERS,
            self._default(),
            wire_proxy_url="http://127.0.0.1:8083",
            run_id="RUN-9",
        )
        assert isinstance(proxy, LabHttpProxy)
        self.assertEqual(proxy._client.headers.get(WIRE_RUN_HEADER), "RUN-9")

    def test_declared_url_threads_run_id(self) -> None:
        proxy = resolve_proxy(
            {"server": "decl"},
            self.SERVERS,
            self._default(),
            wire_proxy_url="http://127.0.0.1:8083",
            run_id="RUN-9",
        )
        assert isinstance(proxy, LabHttpProxy)
        self.assertEqual(proxy._client.headers.get(WIRE_RUN_HEADER), "RUN-9")

    def test_no_run_id_means_no_header(self) -> None:
        proxy = resolve_proxy(
            {"server": "lab-gh"},
            self.SERVERS,
            self._default(),
            wire_proxy_url="http://127.0.0.1:8083",
        )
        assert isinstance(proxy, LabHttpProxy)
        self.assertNotIn(WIRE_RUN_HEADER, proxy._client.headers)


if __name__ == "__main__":
    unittest.main()
