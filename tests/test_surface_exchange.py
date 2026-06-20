"""Discovery-vs-exchange overlay (recette/surface/exchange.py): pure, I4.

Composes the surface judge (per-agent hook detection) with the reconcile join
(per-exchange identified vs ghost). Asserts: a hook exchange is identified and
its agent is detected; a wire-only flow to a non-mediated target is a ghost
exchange (not identified, reason carried); and the whole report is byte-stable
on replay (I4).
"""

from __future__ import annotations

import json
import unittest

from recette.surface.exchange import build_exchange_report

_ALLOW = {"127.0.0.1:8082"}


def _hook_trace(seq: int, agent_id: str) -> dict:
    """Minimal ProxyTrace view of a mediated call (the hook exchange)."""
    return {
        "seq": seq,
        "agent_id": agent_id,
        "target_system": "github",
        "action_type": "open_pr",
        "resource": "octo/repo",
        "run_id": "run-1",
    }


def _ghost_flow(seq: int, host: str, port: int) -> dict:
    """A wire flow to a NON-mediated target: no audited side effect behind it."""
    return {"seq": seq, "method": "POST", "host": host, "port": port, "path": "/leak"}


def _build(traces: list[dict], flows: list[dict]):
    return build_exchange_report(
        proxy_traces=traces, wire_flows=flows, allowlist=_ALLOW, run_id="run-1"
    )


class TestExchangeReport(unittest.TestCase):
    def test_hook_exchange_identified_and_agent_detected(self) -> None:
        report = _build([_hook_trace(1, "pr-bot")], [])
        data = report.to_dict()
        self.assertEqual(data["ghost_exchanges"], 0)
        self.assertTrue(data["scorecard"]["ok"])
        self.assertEqual(data["scorecard"]["false_negatives"], [])
        # one agent, detected on the hook surfaces
        self.assertEqual([a["agent_id"] for a in data["agents"]], ["pr-bot"])
        self.assertTrue(data["agents"][0]["detected_anywhere"])
        # the hook exchange is identified
        hook = [e for e in data["exchanges"] if e["kind"] == "hook"]
        self.assertEqual(len(hook), 1)
        self.assertTrue(hook[0]["identified"])
        self.assertEqual(hook[0]["agent_id"], "pr-bot")
        # each exchange carries its originating run (client-side run filter)
        self.assertEqual(hook[0]["run_id"], "run-1")

    def test_per_agent_wire_surface_not_claimed(self) -> None:
        # A wire flow exists, but per-agent detection must NOT claim ebpf_wire
        # (wire is unattributable to an agent). The agent is hook-only.
        report = _build([_hook_trace(1, "pr-bot")], [_ghost_flow(2, "evil.test", 443)])
        agent = report.to_dict()["agents"][0]
        wire = [s for s in agent["per_surface"] if s["surface"] == "ebpf_wire"][0]
        self.assertFalse(wire["detected"])

    def test_wire_only_flow_is_a_ghost_exchange(self) -> None:
        report = _build([_hook_trace(1, "pr-bot")], [_ghost_flow(2, "evil.test", 443)])
        data = report.to_dict()
        self.assertEqual(data["ghost_exchanges"], 1)
        wire = [e for e in data["exchanges"] if e["kind"] == "wire"]
        self.assertEqual(len(wire), 1)
        self.assertFalse(wire[0]["identified"])
        self.assertEqual(wire[0]["reason"], "non_mediated_target")
        self.assertIsNone(wire[0]["agent_id"])

    def test_exchanges_sorted_by_kind_then_seq(self) -> None:
        report = _build(
            [_hook_trace(3, "a"), _hook_trace(1, "b")],
            [_ghost_flow(5, "evil.test", 1), _ghost_flow(4, "evil.test", 2)],
        )
        keys = [(e["kind"], e["seq"]) for e in report.to_dict()["exchanges"]]
        self.assertEqual(keys, [("hook", 1), ("hook", 3), ("wire", 4), ("wire", 5)])

    def test_report_is_byte_stable_on_replay(self) -> None:
        traces = [_hook_trace(1, "pr-bot"), _hook_trace(2, "issue-bot")]
        flows = [_ghost_flow(3, "evil.test", 443)]
        first = json.dumps(_build(traces, flows).to_dict(), sort_keys=True)
        second = json.dumps(_build(traces, flows).to_dict(), sort_keys=True)
        self.assertEqual(first, second)

    def test_empty_buffers_yield_empty_report(self) -> None:
        data = _build([], []).to_dict()
        self.assertEqual(data["agents"], [])
        self.assertEqual(data["exchanges"], [])
        self.assertEqual(data["ghost_exchanges"], 0)
        self.assertTrue(data["scorecard"]["ok"])


if __name__ == "__main__":
    unittest.main()
