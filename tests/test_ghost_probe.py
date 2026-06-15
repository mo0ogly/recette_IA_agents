"""Ghost-probe request builder is deterministic and carries the run header.

The live egress (direct_write) is proven in scripts/smoke_reconcile.py (R14);
here we assert the pure request shape: a POST to the sink, JSON body, and the
wire run header so the recorded WireFlow is attributable to the run.
"""

from __future__ import annotations

import json
import unittest

from recette.redteam_ghost_probe import DEFAULT_RUN_HEADER, build_probe_request


class GhostProbeRequestTest(unittest.TestCase):
    def test_request_targets_sink_with_post_and_json_body(self) -> None:
        req = build_probe_request(
            "http://127.0.0.1:9113/shadow_db/write", {"row": "secret"}, run_id="R1"
        )
        self.assertEqual(req.method, "POST")
        self.assertEqual(req.full_url, "http://127.0.0.1:9113/shadow_db/write")
        self.assertEqual(req.get_header("Content-type"), "application/json")
        self.assertEqual(json.loads(req.data.decode("utf-8")), {"row": "secret"})

    def test_run_id_rides_the_wire_run_header(self) -> None:
        req = build_probe_request("http://127.0.0.1:9113/x", {}, run_id="R7")
        # urllib capitalizes header keys; query via the canonical lookup.
        self.assertEqual(req.get_header(DEFAULT_RUN_HEADER.capitalize()), "R7")

    def test_no_run_id_means_no_run_header(self) -> None:
        req = build_probe_request("http://127.0.0.1:9113/x", {})
        self.assertIsNone(req.get_header(DEFAULT_RUN_HEADER.capitalize()))

    def test_body_is_byte_stable(self) -> None:
        a = build_probe_request("http://h/x", {"b": 2, "a": 1}).data
        b = build_probe_request("http://h/x", {"a": 1, "b": 2}).data
        self.assertEqual(a, b)  # sort_keys -> deterministic body


if __name__ == "__main__":
    unittest.main()
