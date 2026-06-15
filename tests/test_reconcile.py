"""Wire-vs-audit reconciliation (allowlist slice): pure, deterministic (I4).

A legitimate run only talks to mediated targets. Any wire flow whose target host
is outside the allowlist is an unmediated path (the ghost-agent signal). reconcile
is a pure function of (flows, allowlist): no clock, no network, byte-stable.
"""

from __future__ import annotations

import unittest

from recette.platform.proxy.reconcile import (
    ReconcileReport,
    build_allowlist,
    reconcile,
)


def _flow(seq: int, host: str) -> dict:
    """Minimal wire-flow view: only host + seq matter for the allowlist diff."""
    return {"seq": seq, "host": host}


class TestReconcile(unittest.TestCase):
    def test_clean_run_has_no_bypass(self) -> None:
        flows = [_flow(1, "127.0.0.1:8082"), _flow(2, "127.0.0.1:9101")]
        allow = {"127.0.0.1:8082", "127.0.0.1:9101"}
        report = reconcile(flows, allow)
        self.assertIsInstance(report, ReconcileReport)
        self.assertTrue(report.ok)
        self.assertEqual(report.bypass_flows, [])

    def test_flow_outside_allowlist_is_a_bypass(self) -> None:
        flows = [_flow(1, "127.0.0.1:8082"), _flow(2, "127.0.0.1:9113")]
        allow = {"127.0.0.1:8082"}
        report = reconcile(flows, allow)
        self.assertFalse(report.ok)
        self.assertEqual([f["host"] for f in report.bypass_flows], ["127.0.0.1:9113"])

    def test_unclassifiable_empty_host_is_suspect_not_allowed(self) -> None:
        # Fail-safe classification: an empty/garbage host is never silently allowed.
        report = reconcile([_flow(1, "")], {"127.0.0.1:8082"})
        self.assertFalse(report.ok)
        self.assertEqual(len(report.bypass_flows), 1)

    def test_is_deterministic_and_seq_ordered(self) -> None:
        flows = [_flow(2, "evil:1"), _flow(1, "127.0.0.1:8082"), _flow(3, "evil:2")]
        allow = {"127.0.0.1:8082"}
        a = reconcile(flows, allow)
        b = reconcile(flows, allow)
        self.assertEqual(a.to_dict(), b.to_dict())
        self.assertEqual([f["seq"] for f in a.bypass_flows], [2, 3])


class TestAllowlistFromConfig(unittest.TestCase):
    def test_allowlist_includes_lab_mock_local_and_llm_hosts(self) -> None:
        servers = [
            {"id": "gh-mock", "system": "github", "mode": "mock_local", "port": 9101},
            {"id": "direct-sink", "system": "direct_sink", "mode": "honeypot", "port": 9113},
        ]
        allow = build_allowlist(
            servers=servers,
            lab_host="127.0.0.1:8082",
            llm_hosts={"api.groq.com:443"},
        )
        self.assertIn("127.0.0.1:8082", allow)  # the lab
        self.assertIn("127.0.0.1:9101", allow)  # a mock_local server
        self.assertIn("api.groq.com:443", allow)  # an LLM backend
        self.assertNotIn("127.0.0.1:9113", allow)  # the honeypot is NEVER allowlisted


if __name__ == "__main__":
    unittest.main()
