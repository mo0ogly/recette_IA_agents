"""Tests for the probe-vs-wire precision/recall bench (surface/bench_probe_wire).

Pure module: it joins wire flows (ground truth, real ip:port from layers.l3l4)
to probe recordings (connect:ip:port tokens) and scores the detector. No I/O.
"""

from __future__ import annotations

import unittest

from recette.surface.bench_probe_wire import build_bench_report, probe_endpoints, wire_endpoints


def _wire(dst_ip, dst_port, host=None, ja3=None):
    return {
        "host": host,
        "layers": {
            "l3l4": {"dst_ip": dst_ip, "dst_port": dst_port},
            "tls": {"ja3": ja3} if ja3 else {},
        },
    }


def _probe(tokens):
    return [{"agent_id": "a1", "surfaces": {"ebpf_wire": tokens}}]


class WireEndpointsTests(unittest.TestCase):
    def test_extracts_ip_port_and_labels(self) -> None:
        mapping, without_ip = wire_endpoints(
            [_wire("104.18.2.1", 443, host="api.groq.com", ja3="abc")]
        )
        self.assertEqual(without_ip, 0)
        self.assertEqual(mapping["104.18.2.1:443"], {"host": "api.groq.com", "ja3": "abc"})

    def test_counts_flows_without_ip(self) -> None:
        mapping, without_ip = wire_endpoints([{"host": "x", "layers": None}, {"host": "y"}])
        self.assertEqual(mapping, {})
        self.assertEqual(without_ip, 2)


class ProbeEndpointsTests(unittest.TestCase):
    def test_only_connect_tokens(self) -> None:
        eps = probe_endpoints(_probe(["connect:1.2.3.4:443", "dns:api.groq.com", "exec:bot"]))
        self.assertEqual(eps, {"1.2.3.4:443"})


class BenchReportTests(unittest.TestCase):
    def test_tp_fn_fp_and_rates(self) -> None:
        wire = [
            _wire("104.18.2.1", 443, host="api.groq.com", ja3="j1"),  # shared -> TP
            _wire("203.0.113.9", 443, host="evil.net", ja3="j2"),  # wire-only -> FN (missed)
        ]
        probe = _probe(["connect:104.18.2.1:443", "connect:8.8.8.8:53"])  # 8.8.8.8 -> FP
        report = build_bench_report(wire, probe).to_dict()
        self.assertEqual((report["tp"], report["fn"], report["fp"]), (1, 1, 1))
        self.assertEqual(report["precision"], 0.5)
        self.assertEqual(report["recall"], 0.5)
        self.assertEqual(report["f1"], 0.5)
        verdicts = {e["endpoint"]: e["verdict"] for e in report["endpoints"]}
        self.assertEqual(verdicts["104.18.2.1:443"], "tp")
        self.assertEqual(verdicts["203.0.113.9:443"], "fn")
        self.assertEqual(verdicts["8.8.8.8:53"], "fp")

    def test_fn_row_keeps_wire_label(self) -> None:
        report = build_bench_report(
            [_wire("203.0.113.9", 443, host="evil.net", ja3="j2")], _probe([])
        ).to_dict()
        fn = report["endpoints"][0]
        self.assertEqual(fn["verdict"], "fn")
        self.assertEqual(fn["host"], "evil.net")
        self.assertEqual(fn["ja3"], "j2")

    def test_undefined_rates_are_none_not_zero(self) -> None:
        # No probe detections at all: precision undefined (no TP+FP), recall 0.
        report = build_bench_report([_wire("1.1.1.1", 443)], _probe([])).to_dict()
        self.assertIsNone(report["precision"])
        self.assertEqual(report["recall"], 0.0)
        self.assertIsNone(report["f1"])

    def test_perfect_detection(self) -> None:
        report = build_bench_report(
            [_wire("1.1.1.1", 443)], _probe(["connect:1.1.1.1:443"])
        ).to_dict()
        self.assertEqual((report["tp"], report["fn"], report["fp"]), (1, 0, 0))
        self.assertEqual(report["recall"], 1.0)
        self.assertEqual(report["precision"], 1.0)
        self.assertEqual(report["f1"], 1.0)

    def test_partial_coverage_surfaced(self) -> None:
        report = build_bench_report(
            [_wire("1.1.1.1", 443), {"host": "legacy", "layers": None}], _probe([])
        ).to_dict()
        self.assertEqual(report["wire_flows_without_ip"], 1)


if __name__ == "__main__":
    unittest.main()
