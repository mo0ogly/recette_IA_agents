"""End-to-end test: HttpSourceScanAdapter <-> live mock Discovery server <-> oracle.

Starts the stdlib mock on an ephemeral port in a background thread and drives it through
the real HttpSourceScanAdapter (stdlib client), proving the assumed :8081 routes work and
the full discovery recette passes over HTTP.
"""

from __future__ import annotations

import threading
import unittest

from recette._http_client import StdlibHttpClient
from recette.discovery_harness import run_discovery_recette
from recette.discovery_mock import make_server
from recette.http_adapter import HttpSourceScanAdapter


class TestDiscoveryMockEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server(host="127.0.0.1", port=0)  # ephemeral port
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join(timeout=5)

    def _adapter(self):
        base = f"http://127.0.0.1:{self.port}"
        client = StdlibHttpClient(base, headers={"X-Tenant-Id": "dev"})
        return HttpSourceScanAdapter(base_url=base, client=client)

    def test_full_discovery_recette_over_http_passes(self):
        scorecard = run_discovery_recette(self._adapter())
        self.assertTrue(scorecard.all_passed, "\n" + scorecard.render())
        self.assertEqual(scorecard.false_positives, 0)
        self.assertEqual(scorecard.false_negatives, 0)
        self.assertTrue(scorecard.ordering_ok)


if __name__ == "__main__":
    unittest.main()
