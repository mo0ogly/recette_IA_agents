"""Wire-vs-audit reconciliation (allowlist slice): pure, deterministic (I4).

A legitimate run only talks to mediated targets. Any wire flow whose target host
is outside the allowlist is an unmediated path (the ghost-agent signal). reconcile
is a pure function of (flows, allowlist): no clock, no network, byte-stable.
"""

from __future__ import annotations

import json
import unittest

from recette.platform.proxy.protocol import side_effect_hash
from recette.platform.proxy.reconcile import (
    ReconcileReport,
    build_allowlist,
    reconcile,
    reconcile_run,
    reconcile_strict,
    target_of,
    wire_flow_side_effect_hash,
)


def _flow(seq: int, host: str, port: int = 0) -> dict:
    """Minimal wire-flow view (matches WireFlow.to_dict: host + port separate)."""
    return {"seq": seq, "host": host, "port": port}


class TestReconcile(unittest.TestCase):
    def test_clean_run_has_no_bypass(self) -> None:
        flows = [_flow(1, "127.0.0.1", 8082), _flow(2, "127.0.0.1", 9101)]
        allow = {"127.0.0.1:8082", "127.0.0.1:9101"}
        report = reconcile(flows, allow)
        self.assertIsInstance(report, ReconcileReport)
        self.assertTrue(report.ok)
        self.assertEqual(report.bypass_flows, [])

    def test_localhost_alias_matches_127(self) -> None:
        # mitmproxy may name the local host "localhost"; it must match a
        # 127.0.0.1 allowlist entry.
        report = reconcile([_flow(1, "localhost", 8082)], {"127.0.0.1:8082"})
        self.assertTrue(report.ok)
        self.assertEqual(target_of(_flow(1, "localhost", 8082)), "127.0.0.1:8082")

    def test_flow_outside_allowlist_is_a_bypass(self) -> None:
        flows = [_flow(1, "127.0.0.1", 8082), _flow(2, "127.0.0.1", 9113)]
        allow = {"127.0.0.1:8082"}
        report = reconcile(flows, allow)
        self.assertFalse(report.ok)
        self.assertEqual([f["port"] for f in report.bypass_flows], [9113])

    def test_unclassifiable_empty_host_is_suspect_not_allowed(self) -> None:
        # Fail-safe classification: an empty/garbage host is never silently allowed.
        report = reconcile([_flow(1, "", 0)], {"127.0.0.1:8082"})
        self.assertFalse(report.ok)
        self.assertEqual(len(report.bypass_flows), 1)

    def test_is_deterministic_and_seq_ordered(self) -> None:
        flows = [_flow(2, "evil.test", 1), _flow(1, "127.0.0.1", 8082), _flow(3, "evil.test", 2)]
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


class TestReconcileRun(unittest.TestCase):
    """The wire<->audit join (step 4): a wire flow to a non-mediated target has
    no matching ProxyTrace -> bypass; the run's audited side-effects are the
    audit-view half of the reconciliation."""

    @staticmethod
    def _run_flow(seq: int, host: str, port: int, run_id: str) -> dict:
        return {"seq": seq, "host": host, "port": port, "run_id": run_id}

    @staticmethod
    def _trace(run_id: str, target_system: str = "github") -> dict:
        return {"run_id": run_id, "target_system": target_system, "side_effect_hash": "h"}

    def test_direct_write_to_non_mediated_target_is_unaudited_bypass(self) -> None:
        flows = [
            self._run_flow(1, "127.0.0.1", 8082, "R"),  # mediated lab egress
            self._run_flow(2, "127.0.0.1", 9113, "R"),  # ghost: direct shadow-db write
        ]
        traces = [self._trace("R")]  # only the lab action produced an audit event
        report = reconcile_run(flows, traces, {"127.0.0.1:8082"})
        self.assertFalse(report.ok)
        self.assertEqual([f["port"] for f in report.bypass_flows], [9113])
        # The run WAS otherwise audited: a legit ProxyTrace exists for it, which
        # sharpens the signal (audited run + an unaudited egress).
        self.assertIn("R", report.audited_run_ids)

    def test_all_mediated_flows_reconcile_ok(self) -> None:
        flows = [self._run_flow(1, "127.0.0.1", 8082, "R")]
        report = reconcile_run(flows, [self._trace("R")], {"127.0.0.1:8082"})
        self.assertTrue(report.ok)
        self.assertEqual(report.bypass_flows, [])

    def test_join_is_deterministic(self) -> None:
        flows = [
            self._run_flow(2, "127.0.0.1", 9113, "R"),
            self._run_flow(1, "127.0.0.1", 8082, "R"),
        ]
        traces = [self._trace("R")]
        a = reconcile_run(flows, traces, {"127.0.0.1:8082"})
        b = reconcile_run(flows, traces, {"127.0.0.1:8082"})
        self.assertEqual(a.to_dict(), b.to_dict())
        self.assertEqual([f["seq"] for f in a.bypass_flows], [2])


def _exec_flow(seq: int, port: int, *, action: str = "open_pr", resource: str = "acme/x") -> dict:
    """A governed-action wire flow (/{ts}/execute), shaped like LabHttpProxy's call."""
    return {
        "seq": seq,
        "host": "127.0.0.1",
        "port": port,
        "path": "/github/execute",
        "request_body": json.dumps({"action_type": action, "resource": resource, "payload": {}}),
        "response_body": json.dumps({"success": True, "data": {"number": 42}}),
        "run_id": "R",
    }


def _trace_for(action: str = "open_pr", resource: str = "acme/x") -> dict:
    """A ProxyTrace whose side_effect_hash matches _exec_flow's recomputed hash."""
    response = {"number": 42}
    return {
        "run_id": "R",
        "side_effect_hash": side_effect_hash("github", action, resource, response),
    }


class TestReconcileStrict(unittest.TestCase):
    """Phase 3: per-flow side_effect_hash join catches a ghost hitting an
    ALLOWLISTED target directly (no matching ProxyTrace)."""

    def test_recomputes_the_proxy_hash_from_a_wire_flow(self) -> None:
        self.assertEqual(
            wire_flow_side_effect_hash(_exec_flow(1, 9101)),
            side_effect_hash("github", "open_pr", "acme/x", {"number": 42}),
        )

    def test_non_execute_flow_has_no_recomputable_hash(self) -> None:
        health = {"seq": 1, "host": "127.0.0.1", "port": 9101, "path": "/health"}
        self.assertIsNone(wire_flow_side_effect_hash(health))

    def test_mediated_action_with_matching_audit_event_is_ok(self) -> None:
        report = reconcile_strict([_exec_flow(1, 9101)], [_trace_for()], {"127.0.0.1:9101"})
        self.assertTrue(report.ok)
        self.assertEqual(report.bypass_flows, [])

    def test_ghost_via_allowlisted_target_is_flagged_no_audit_event(self) -> None:
        # A governed-shaped write to an allowlisted server with NO matching trace:
        # phase 2 (target allowlist) would MISS this; phase 3 catches it.
        report = reconcile_strict([_exec_flow(1, 9101)], [], {"127.0.0.1:9101"})
        self.assertFalse(report.ok)
        self.assertEqual([f["bypass_reason"] for f in report.bypass_flows], ["no_audit_event"])

    def test_non_mediated_target_still_flagged(self) -> None:
        ghost = {"seq": 1, "host": "127.0.0.1", "port": 9113, "path": "/shadow_db/write"}
        report = reconcile_strict([ghost], [], {"127.0.0.1:9101"})
        self.assertEqual([f["bypass_reason"] for f in report.bypass_flows], ["non_mediated_target"])

    def test_benign_health_traffic_to_mediated_target_not_flagged(self) -> None:
        health = {"seq": 1, "host": "127.0.0.1", "port": 9101, "path": "/health"}
        report = reconcile_strict([health], [], {"127.0.0.1:9101"})
        self.assertTrue(report.ok)

    def test_is_deterministic(self) -> None:
        flows = [_exec_flow(2, 9101), _exec_flow(1, 9101, action="merge_pr")]
        a = reconcile_strict(flows, [], {"127.0.0.1:9101"})
        b = reconcile_strict(flows, [], {"127.0.0.1:9101"})
        self.assertEqual(a.to_dict(), b.to_dict())


class TestReconcileStrictPersistedHash(unittest.TestCase):
    """The persisted ``side_effect_hash`` column replaces the per-call recompute:
    a flow dict carrying the key must yield the same report as a legacy dict
    without it, and a persisted NULL (key present, value None) is benign."""

    def test_persisted_hash_report_is_byte_identical_to_recompute(self) -> None:
        # Golden equivalence: same flows, one copy with the persisted key
        # (precomputed exactly as the store does at insert), one legacy copy
        # without the key -> byte-identical reconciliation.
        legacy = [
            _exec_flow(1, 9101),
            {"seq": 2, "host": "127.0.0.1", "port": 9101, "path": "/health", "run_id": "R"},
        ]
        persisted = [{**f, "side_effect_hash": wire_flow_side_effect_hash(f)} for f in legacy]
        traces = [_trace_for()]
        allow = {"127.0.0.1:9101"}
        a = reconcile_strict(persisted, traces, allow)
        b = reconcile_strict(legacy, traces, allow)
        self.assertEqual(
            json.dumps(a.to_dict(), sort_keys=True),
            json.dumps(b.to_dict(), sort_keys=True),
        )
        self.assertTrue(a.ok)

    def test_persisted_key_wins_over_recompute(self) -> None:
        # The presence of the key short-circuits the JSON re-parse entirely:
        # a governed-shaped flow whose persisted hash matches the audit event
        # reconciles OK even when a recompute over the (here altered) bodies
        # would yield a DIFFERENT hash -- the column is the source of truth.
        altered_body = json.dumps({"success": True, "data": {"number": 999}})
        flow = {**_exec_flow(1, 9101), "response_body": altered_body}
        self.assertIsNotNone(wire_flow_side_effect_hash(flow))  # recompute WOULD diverge
        flow["side_effect_hash"] = wire_flow_side_effect_hash(_exec_flow(1, 9101))
        # Explicit divergence the test relies on: a recompute over the altered
        # bodies yields a hash DIFFERENT from the persisted one.
        self.assertNotEqual(wire_flow_side_effect_hash(flow), flow["side_effect_hash"])
        report = reconcile_strict([flow], [_trace_for()], {"127.0.0.1:9101"})
        self.assertTrue(report.ok)
        self.assertEqual(report.bypass_flows, [])

    def test_persisted_none_hash_is_benign_for_allowlisted_flow(self) -> None:
        # Key present with value None = non-governed flow persisted as NULL:
        # benign on an allowlisted target, never flagged no_audit_event.
        flow = {
            "seq": 1,
            "host": "127.0.0.1",
            "port": 9101,
            "path": "/health",
            "run_id": "R",
            "side_effect_hash": None,
        }
        report = reconcile_strict([flow], [], {"127.0.0.1:9101"})
        self.assertTrue(report.ok)
        self.assertEqual(report.bypass_flows, [])


if __name__ == "__main__":
    unittest.main()
